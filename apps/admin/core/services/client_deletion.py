"""
Eliminación definitiva de un tenant NegocioListo.

TNL-CLIENT-DELETION-SERVICE-V1

La operación:
- suspende el tenant;
- cierra sesiones;
- elimina Evolution / WhatsApp;
- elimina OAuth local MP / Google;
- archiva Typebots privados;
- elimina archivos propios de productos;
- elimina datos tenant;
- elimina usuarios exclusivos;
- elimina Empresa.

Nunca debe eliminar PlantillaMaestra.
"""

from __future__ import annotations

from django.contrib.auth import (
    get_user_model,
)
from django.db import transaction
from django.db.models.deletion import (
    Collector,
    ProtectedError,
    RestrictedError,
)
from django.db import DEFAULT_DB_ALIAS


class ClientDeletionError(
    RuntimeError
):
    pass


class ClientDeletionPreflightError(
    ClientDeletionError
):
    pass


class ClientDeletionPartialError(
    ClientDeletionError
):
    """
    El tenant local pudo quedar eliminado,
    pero quedó pendiente algún archivo físico.
    """

    def __init__(
        self,
        message,
        *,
        result=None,
    ):
        super().__init__(message)
        self.result = result or {}


_ALLOWED_PROTECTED = {
    "core.Pago",
    "core.ConsumoIA",
}


def _extraer_typebot(
    response,
):
    if not isinstance(
        response,
        dict,
    ):
        return {}

    data = response.get(
        "data"
    )

    if not isinstance(
        data,
        dict,
    ):
        return {}

    nested = data.get(
        "typebot"
    )

    if isinstance(
        nested,
        dict,
    ):
        return nested

    return data


def _snapshot_maestros():
    from core.models import PlantillaMaestra

    return tuple(
        PlantillaMaestra.objects
        .order_by("id")
        .values_list(
            "id",
            "slug",
            "identificador_externo",
            "activa",
        )
    )


def _private_typebot_ids(
    empresa,
):
    from core.models import (
        Bot,
        Plantilla,
        PlantillaMaestra,
    )

    master_ids = {
        str(value or "").strip()
        for value in (
            PlantillaMaestra.objects
            .values_list(
                "identificador_externo",
                flat=True,
            )
        )
        if str(
            value or ""
        ).strip()
    }

    values = set()

    for value in (
        Bot.objects
        .filter(
            empresa=empresa
        )
        .values_list(
            "identificador_externo",
            flat=True,
        )
    ):
        value = str(
            value or ""
        ).strip()

        if value:
            values.add(value)

    for value in (
        Plantilla.objects
        .filter(
            empresa=empresa
        )
        .values_list(
            "identificador_externo",
            flat=True,
        )
    ):
        value = str(
            value or ""
        ).strip()

        if value:
            values.add(value)

    if values & master_ids:
        raise ClientDeletionPreflightError(
            "SEGURIDAD: el tenant referencia "
            "un Typebot maestro."
        )

    for external_id in values:

        other_bot = (
            Bot.objects
            .exclude(
                empresa=empresa
            )
            .filter(
                identificador_externo=
                    external_id
            )
            .exists()
        )

        other_template = (
            Plantilla.objects
            .exclude(
                empresa=empresa
            )
            .filter(
                identificador_externo=
                    external_id
            )
            .exists()
        )

        if (
            other_bot
            or
            other_template
        ):
            raise ClientDeletionPreflightError(
                "SEGURIDAD: un Typebot privado "
                "está referenciado por otra empresa."
            )

    return tuple(
        sorted(
            values
        )
    )


def _validar_usuarios(
    empresa,
):
    from core.models import (
        PerfilUsuario,
    )

    perfiles = list(
        PerfilUsuario.objects
        .filter(
            empresa=empresa
        )
        .select_related(
            "usuario"
        )
        .order_by("id")
    )

    user_ids = []

    for perfil in perfiles:

        user = perfil.usuario

        if (
            user.is_staff
            or
            user.is_superuser
        ):
            raise ClientDeletionPreflightError(
                "SEGURIDAD: el tenant contiene "
                "una cuenta administrativa Django."
            )

        if (
            PerfilUsuario.objects
            .filter(
                usuario=user
            )
            .count()
            != 1
        ):
            raise ClientDeletionPreflightError(
                "SEGURIDAD: una cuenta de usuario "
                "no es exclusiva del tenant."
            )

        if str(
            perfil.rol
            or ""
        ).strip() == "administrador":
            raise ClientDeletionPreflightError(
                "SEGURIDAD: el tenant contiene "
                "un perfil administrador."
            )

        user_ids.append(
            user.id
        )

    return tuple(
        sorted(
            set(
                user_ids
            )
        )
    )


def _validar_protected(
    empresa,
):
    collector = Collector(
        using=DEFAULT_DB_ALIAS
    )

    try:

        collector.collect(
            [empresa]
        )

    except ProtectedError as exc:

        labels = {
            obj._meta.label
            for obj
            in exc.protected_objects
        }

        unknown = (
            labels
            -
            _ALLOWED_PROTECTED
        )

        if unknown:
            raise ClientDeletionPreflightError(
                "Existen nuevas dependencias "
                "PROTECT no contempladas."
            )

        return tuple(
            sorted(
                labels
            )
        )

    except RestrictedError as exc:

        raise ClientDeletionPreflightError(
            "Existen dependencias RESTRICT "
            "que impiden eliminar el tenant."
        ) from exc

    return ()


def _capturar_archivos(
    empresa,
):
    from core.models import (
        Producto,
        ProductoImagen,
    )

    rows = []
    seen = set()

    for producto in (
        Producto.objects
        .filter(
            catalogo__empresa=empresa
        )
        .iterator()
    ):

        field = producto.imagen_principal

        if (
            field
            and
            field.name
        ):

            key = (
                id(field.storage),
                field.name,
            )

            if key not in seen:

                seen.add(key)

                rows.append(
                    (
                        field.storage,
                        field.name,
                    )
                )

    for imagen in (
        ProductoImagen.objects
        .filter(
            producto__catalogo__empresa=
                empresa
        )
        .iterator()
    ):

        field = imagen.imagen

        if (
            field
            and
            field.name
        ):

            key = (
                id(field.storage),
                field.name,
            )

            if key not in seen:

                seen.add(key)

                rows.append(
                    (
                        field.storage,
                        field.name,
                    )
                )

    return rows


def plan_eliminacion_cliente(
    empresa_id: int,
) -> dict:
    from core.models import (
        Empresa,
        Licencia,
        PerfilUsuario,
        InstalacionPlantilla,
        Plantilla,
        Bot,
        Canal,
        Catalogo,
        Producto,
        Pedido,
        Pago,
        Cita,
        ConfiguracionMercadoPago,
        ConfiguracionGoogleCalendar,
        ConfiguracionAgenda,
        HorarioAtencion,
        ConfiguracionIA,
        BolsaIA,
        ConsumoIA,
        AceptacionTerminos,
    )

    empresa = (
        Empresa.objects
        .get(
            pk=empresa_id
        )
    )

    user_ids = (
        _validar_usuarios(
            empresa
        )
    )

    protected = (
        _validar_protected(
            empresa
        )
    )

    private_ids = (
        _private_typebot_ids(
            empresa
        )
    )

    files = (
        _capturar_archivos(
            empresa
        )
    )

    return {
        "empresa_id":
            empresa.id,

        "users":
            len(user_ids),

        "protected_models":
            protected,

        "private_typebots":
            len(private_ids),

        "physical_files":
            len(files),

        "counts": {
            "licencias":
                Licencia.objects
                .filter(
                    empresa=empresa
                )
                .count(),

            "perfiles":
                PerfilUsuario.objects
                .filter(
                    empresa=empresa
                )
                .count(),

            "instalaciones":
                InstalacionPlantilla.objects
                .filter(
                    empresa=empresa
                )
                .count(),

            "plantillas":
                Plantilla.objects
                .filter(
                    empresa=empresa
                )
                .count(),

            "bots":
                Bot.objects
                .filter(
                    empresa=empresa
                )
                .count(),

            "canales":
                Canal.objects
                .filter(
                    bot__empresa=empresa
                )
                .count(),

            "catalogos":
                Catalogo.objects
                .filter(
                    empresa=empresa
                )
                .count(),

            "productos":
                Producto.objects
                .filter(
                    catalogo__empresa=empresa
                )
                .count(),

            "pedidos":
                Pedido.objects
                .filter(
                    empresa=empresa
                )
                .count(),

            "pagos":
                Pago.objects
                .filter(
                    pedido__empresa=empresa
                )
                .count(),

            "citas":
                Cita.objects
                .filter(
                    empresa=empresa
                )
                .count(),

            "mp":
                ConfiguracionMercadoPago.objects
                .filter(
                    empresa=empresa
                )
                .count(),

            "google":
                ConfiguracionGoogleCalendar.objects
                .filter(
                    empresa=empresa
                )
                .count(),

            "agenda":
                ConfiguracionAgenda.objects
                .filter(
                    empresa=empresa
                )
                .count(),

            "horarios":
                HorarioAtencion.objects
                .filter(
                    empresa=empresa
                )
                .count(),

            "ia_config":
                ConfiguracionIA.objects
                .filter(
                    empresa=empresa
                )
                .count(),

            "bolsas":
                BolsaIA.objects
                .filter(
                    empresa=empresa
                )
                .count(),

            "consumos":
                ConsumoIA.objects
                .filter(
                    empresa=empresa
                )
                .count(),

            "aceptaciones":
                AceptacionTerminos.objects
                .filter(
                    empresa=empresa
                )
                .count(),
        },
    }


def _preflight_typebots_remotos(
    external_ids,
):
    from core.integrations.typebot_client import (
        TypebotClient,
    )

    client = TypebotClient()

    states = {}

    for external_id in external_ids:

        try:

            response = (
                client.obtener_typebot(
                    external_id
                )
            )

        except Exception as exc:

            raise ClientDeletionPreflightError(
                "No fue posible validar "
                "un Typebot privado."
            ) from exc

        status = response.get(
            "status"
        )

        if status == 404:
            states[
                external_id
            ] = "missing"

            continue

        if not response.get(
            "ok"
        ):

            raise ClientDeletionPreflightError(
                "Un Typebot privado respondió "
                "un estado inesperado."
            )

        typebot = (
            _extraer_typebot(
                response
            )
        )

        returned_id = str(
            typebot.get(
                "id"
            )
            or ""
        ).strip()

        if (
            returned_id
            and
            returned_id != external_id
        ):
            raise ClientDeletionPreflightError(
                "SEGURIDAD: Typebot devolvió "
                "una identidad distinta."
            )

        states[
            external_id
        ] = (
            "archived"
            if typebot.get(
                "isArchived"
            ) is True
            else
            "active"
        )

    return (
        client,
        states,
    )


def _archivar_typebots(
    client,
    states,
) -> dict:

    archived = 0
    already_absent = 0
    already_archived = 0

    for (
        external_id,
        state,
    ) in states.items():

        if state == "missing":

            already_absent += 1
            continue

        if state == "archived":

            already_archived += 1
            continue

        response = (
            client.eliminar_typebot(
                external_id
            )
        )

        #
        # Incluso si DELETE devuelve algo
        # inesperado, la comprobación final
        # es la autoridad.
        #
        verify = (
            client.obtener_typebot(
                external_id
            )
        )

        if verify.get(
            "status"
        ) == 404:

            archived += 1
            continue

        if not verify.get(
            "ok"
        ):

            raise ClientDeletionError(
                "No fue posible comprobar "
                "el archivado de Typebot."
            )

        typebot = (
            _extraer_typebot(
                verify
            )
        )

        if typebot.get(
            "isArchived"
        ) is not True:

            raise ClientDeletionError(
                "El Typebot privado continúa "
                "operativo después de DELETE."
            )

        archived += 1

    return {
        "archived":
            archived,

        "already_absent":
            already_absent,

        "already_archived":
            already_archived,
    }


def _eliminar_archivos(
    files,
):
    deleted = 0
    missing = 0
    errors = 0

    for storage, name in files:

        try:

            if storage.exists(
                name
            ):

                storage.delete(
                    name
                )

                if storage.exists(
                    name
                ):
                    errors += 1
                else:
                    deleted += 1

            else:

                missing += 1

        except Exception:

            errors += 1

    return {
        "deleted":
            deleted,

        "missing":
            missing,

        "errors":
            errors,
    }


def eliminar_cliente_definitivamente(
    empresa_id: int,
    *,
    dry_run: bool = False,
) -> dict:

    from core.models import (
        Empresa,
        PerfilUsuario,
        Pago,
        ConsumoIA,
    )

    from core.services.client_lifecycle import (
        desactivar_empresa_admin,
        cerrar_sesiones_empresa,
    )

    from core.services.client_connection_reset import (
        restablecer_conexiones_empresa,
    )

    User = get_user_model()

    #
    # PREFLIGHT LOCAL COMPLETO
    #
    plan = (
        plan_eliminacion_cliente(
            empresa_id
        )
    )

    if dry_run:

        return {
            **plan,
            "dry_run":
                True,
        }


    empresa = (
        Empresa.objects
        .get(
            pk=empresa_id
        )
    )

    master_before = (
        _snapshot_maestros()
    )

    if not master_before:

        raise ClientDeletionPreflightError(
            "No existe biblioteca maestra "
            "para certificar la eliminación."
        )


    user_ids = (
        _validar_usuarios(
            empresa
        )
    )

    external_ids = (
        _private_typebot_ids(
            empresa
        )
    )

    files = (
        _capturar_archivos(
            empresa
        )
    )


    #
    # PREFLIGHT REMOTO READ-ONLY
    #
    typebot_client, typebot_states = (
        _preflight_typebots_remotos(
            external_ids
        )
    )


    #
    # Suspender primero.
    # Si una fase externa falla, el tenant
    # queda cerrado y puede reintentarse.
    #
    suspension = (
        desactivar_empresa_admin(
            empresa_id
        )
    )


    #
    # Typebots privados.
    #
    typebots = (
        _archivar_typebots(
            typebot_client,
            typebot_states,
        )
    )


    #
    # A2 elimina Evolution + OAuth local.
    #
    reset = (
        restablecer_conexiones_empresa(
            empresa_id
        )
    )


    #
    # Cierre adicional idempotente.
    #
    sessions_closed = (
        cerrar_sesiones_empresa(
            empresa_id
        )
    )


    #
    # Revalidar grafo justo antes
    # de la destrucción local.
    #
    empresa = (
        Empresa.objects
        .get(
            pk=empresa_id
        )
    )

    _validar_usuarios(
        empresa
    )

    _validar_protected(
        empresa
    )


    #
    # ELIMINACION LOCAL TRANSACCIONAL
    #
    with transaction.atomic():

        locked = (
            Empresa.objects
            .select_for_update()
            .get(
                pk=empresa_id
            )
        )

        #
        # Resolver los dos PROTECT conocidos.
        #
        pagos_deleted = (
            Pago.objects
            .filter(
                pedido__empresa_id=
                    empresa_id
            )
            .delete()[0]
        )

        consumos_deleted = (
            ConsumoIA.objects
            .filter(
                empresa_id=
                    empresa_id
            )
            .delete()[0]
        )

        #
        # Los usuarios deben borrarse
        # explícitamente porque
        # PerfilUsuario.empresa = SET_NULL.
        #
        users_deleted = 0

        if user_ids:

            users_deleted = (
                User.objects
                .filter(
                    id__in=user_ids
                )
                .delete()[0]
            )

        #
        # Ahora Empresa puede hacer CASCADE
        # sobre todo el tenant restante.
        #
        local_deleted, detail = (
            locked.delete()
        )


    #
    # Verificación local.
    #
    if (
        Empresa.objects
        .filter(
            pk=empresa_id
        )
        .exists()
    ):

        raise ClientDeletionError(
            "La empresa continúa presente "
            "después de la eliminación."
        )

    if user_ids:

        if (
            User.objects
            .filter(
                id__in=user_ids
            )
            .exists()
        ):

            raise ClientDeletionError(
                "Persisten usuarios del tenant."
            )


    #
    # Las maestras deben ser exactamente
    # las mismas.
    #
    master_after = (
        _snapshot_maestros()
    )

    if master_after != master_before:

        raise ClientDeletionError(
            "SEGURIDAD: cambió la biblioteca "
            "de Plantillas Maestras."
        )


    #
    # Archivos físicos se eliminan DESPUÉS
    # del commit local.
    #
    # Si un storage falla, la empresa ya
    # no existe pero se informa claramente
    # para limpieza manual del archivo huérfano.
    #
    file_result = (
        _eliminar_archivos(
            files
        )
    )


    result = {
        **plan,

        "dry_run":
            False,

        "suspension":
            suspension,

        "typebots":
            typebots,

        "reset":
            reset,

        "sessions_closed":
            sessions_closed,

        "pagos_deleted":
            pagos_deleted,

        "consumos_deleted":
            consumos_deleted,

        "users_deleted":
            users_deleted,

        "local_deleted":
            local_deleted,

        "local_detail":
            detail,

        "files":
            file_result,

        "master_templates_unchanged":
            True,
    }


    if file_result[
        "errors"
    ]:

        raise ClientDeletionPartialError(
            (
                "El tenant fue eliminado, "
                "pero uno o más archivos "
                "físicos requieren limpieza "
                "manual."
            ),
            result=result,
        )


    return result
