"""
Ciclo de vida operativo por empresa.

TNL-CLIENT-LIFECYCLE-SERVICE-V1

Autoridad:

EMPRESA OPERATIVA =
    empresa.estado == activa
    Y
    licencia activa y vigente.

La suspensión NO destruye conexiones.
"""

from __future__ import annotations

from django.utils import timezone


class ClientLifecycleError(Exception):
    pass


class LicenciaNoVigenteError(
    ClientLifecycleError
):
    pass


class LifecycleExternalError(
    ClientLifecycleError
):
    pass


def licencia_vigente_empresa(
    empresa,
    *,
    fecha=None,
):
    from core.models import Licencia

    fecha = (
        fecha
        or
        timezone.localdate()
    )

    return (
        Licencia.objects
        .filter(
            empresa=empresa,
            estado=
                Licencia.Estado.ACTIVA,
            fecha_inicio__lte=fecha,
            fecha_fin__gte=fecha,
        )
        .order_by(
            "-fecha_fin",
            "-id",
        )
        .first()
    )


def empresa_operativa(
    empresa,
    *,
    fecha=None,
) -> bool:
    from core.models import Empresa

    if empresa is None:
        return False

    if (
        empresa.estado
        !=
        Empresa.Estado.ACTIVA
    ):
        return False

    return bool(
        licencia_vigente_empresa(
            empresa,
            fecha=fecha,
        )
    )


def usuario_puede_iniciar_sesion(
    user,
) -> bool:
    from django.core.exceptions import (
        ObjectDoesNotExist,
    )

    from core.models import PerfilUsuario

    if (
        user is None
        or
        not getattr(
            user,
            "is_authenticated",
            False,
        )
    ):
        return False

    if getattr(
        user,
        "is_superuser",
        False,
    ):
        return True

    try:
        perfil = (
            user.perfil_negociolisto
        )

    except (
        ObjectDoesNotExist,
        AttributeError,
    ):
        # Preserva cuentas administrativas Django
        # que no utilicen PerfilUsuario.
        return bool(
            getattr(
                user,
                "is_staff",
                False,
            )
        )

    if not perfil.activo:
        return False

    if (
        perfil.rol
        ==
        PerfilUsuario.Rol.ADMINISTRADOR
    ):
        return True

    if perfil.empresa_id is None:
        return False

    return empresa_operativa(
        perfil.empresa
    )


def cerrar_sesiones_empresa(
    empresa_id: int,
) -> int:
    from django.contrib.sessions.models import (
        Session,
    )

    from core.models import PerfilUsuario

    user_ids = set(
        PerfilUsuario.objects
        .filter(
            empresa_id=empresa_id
        )
        .values_list(
            "usuario_id",
            flat=True,
        )
    )

    if not user_ids:
        return 0

    keys = []

    for session in (
        Session.objects
        .all()
        .iterator()
    ):

        try:
            data = session.get_decoded()

        except Exception:
            continue

        raw_user_id = data.get(
            "_auth_user_id"
        )

        try:
            user_id = int(
                raw_user_id
            )

        except (
            TypeError,
            ValueError,
        ):
            continue

        if user_id in user_ids:
            keys.append(
                session.session_key
            )

    if not keys:
        return 0

    deleted, _detail = (
        Session.objects
        .filter(
            session_key__in=keys
        )
        .delete()
    )

    return int(deleted)


def _normalizar_debounce(
    value,
) -> int:
    try:
        value = int(value)
    except (
        TypeError,
        ValueError,
    ):
        return 3

    if not 1 <= value <= 30:
        return 3

    return value


def _sincronizar_whatsapp_empresa(
    empresa_id: int,
    *,
    habilitar: bool,
    dry_run: bool = False,
    strict: bool = False,
) -> dict:
    """
    Sólo cambia enabled de la integración
    Typebot existente.

    NO logout.
    NO elimina instancia.
    NO elimina QR.
    NO elimina Canal.
    """

    from core.models import Canal

    from core.integrations.evolution_client import (
        EvolutionClient,
    )

    client = EvolutionClient()

    canales = (
        Canal.objects
        .filter(
            bot__empresa_id=empresa_id,
            tipo="whatsapp",
        )
        .select_related(
            "bot",
            "bot__empresa",
        )
        .order_by("id")
    )

    revisados = 0
    cambios = 0
    errors = []

    for canal in canales:

        instance = str(
            canal.identificador
            or ""
        ).strip()

        if not instance:
            continue

        revisados += 1

        desired = bool(
            habilitar
            and
            canal.activo
        )

        try:

            rows = [
                row
                for row
                in client._items(
                    client.find_typebots(
                        instance
                    )
                )
                if isinstance(
                    row,
                    dict,
                )
            ]

            if len(rows) != 1:

                errors.append(
                    (
                        instance,
                        "INTEGRATION_COUNT",
                    )
                )

                continue

            integration = rows[0]

            integration_id = (
                integration.get("id")
                or
                integration.get("_id")
            )

            if not integration_id:

                errors.append(
                    (
                        instance,
                        "INTEGRATION_ID_MISSING",
                    )
                )

                continue

            current = bool(
                integration.get(
                    "enabled"
                )
            )

            if current == desired:
                continue

            cambios += 1

            if dry_run:
                continue

            payload = (
                client
                ._nl_typebot_policy_payload(
                    integration,
                    debounce_time=
                        _normalizar_debounce(
                            integration.get(
                                "debounceTime"
                            )
                        ),
                    ignore_jids=
                        integration.get(
                            "ignoreJids"
                        )
                        or [],
                )
            )

            payload[
                "enabled"
            ] = desired

            client.update_typebot_integration(
                instance,
                integration_id,
                payload,
            )

            verify = [
                row
                for row
                in client._items(
                    client.find_typebots(
                        instance
                    )
                )
                if isinstance(
                    row,
                    dict,
                )
            ]

            if (
                len(verify) != 1
                or
                bool(
                    verify[0].get(
                        "enabled"
                    )
                )
                !=
                desired
            ):
                errors.append(
                    (
                        instance,
                        "POST_VERIFY_FAILED",
                    )
                )

        except Exception as exc:

            errors.append(
                (
                    instance,
                    type(exc).__name__,
                )
            )

    if strict and errors:

        raise LifecycleExternalError(
            "No fue posible sincronizar "
            "completamente WhatsApp."
        )

    return {
        "reviewed":
            revisados,

        "changes":
            cambios,

        "errors":
            errors,

        "target_enabled":
            bool(habilitar),

        "dry_run":
            bool(dry_run),
    }


def actualizar_licencias_vencidas(
    empresa,
    *,
    dry_run=False,
) -> int:
    from core.models import Licencia

    hoy = timezone.localdate()

    qs = (
        Licencia.objects
        .filter(
            empresa=empresa,
            estado=
                Licencia.Estado.ACTIVA,
            fecha_fin__lt=hoy,
        )
    )

    cantidad = qs.count()

    if (
        cantidad
        and
        not dry_run
    ):
        qs.update(
            estado=
                Licencia.Estado.VENCIDA,
            actualizado_en=
                timezone.now(),
        )

    return cantidad


def reconciliar_empresa(
    empresa,
    *,
    dry_run=False,
) -> dict:
    """
    Reconcilia una empresa sin destruir
    ninguna conexión.

    Si queda no operativa:
    - invalida sesiones;
    - deshabilita integración Typebot.

    Si queda operativa:
    - habilita Typebot sólo en Canales
      marcados activo=True.
    """

    expired = (
        actualizar_licencias_vencidas(
            empresa,
            dry_run=dry_run,
        )
    )

    # Si acabamos de cambiar estados,
    # calculamos contra BD actual.
    if not dry_run:
        empresa.refresh_from_db(
            fields=[
                "estado",
            ]
        )

    operativa = empresa_operativa(
        empresa
    )

    sesiones = 0

    if (
        not operativa
        and
        not dry_run
    ):
        sesiones = (
            cerrar_sesiones_empresa(
                empresa.id
            )
        )

    whatsapp = (
        _sincronizar_whatsapp_empresa(
            empresa.id,
            habilitar=operativa,
            dry_run=dry_run,
            strict=False,
        )
    )

    return {
        "empresa_id":
            empresa.id,

        "operativa":
            operativa,

        "expired_licenses":
            expired,

        "sessions_closed":
            sesiones,

        "whatsapp":
            whatsapp,

        "external_errors":
            len(
                whatsapp["errors"]
            ),
    }


def reconciliar_todas_empresas(
    *,
    dry_run=False,
) -> dict:
    from core.models import Empresa

    empresas = list(
        Empresa.objects
        .order_by("id")
    )

    results = []

    for empresa in empresas:

        results.append(
            reconciliar_empresa(
                empresa,
                dry_run=dry_run,
            )
        )

    return {
        "companies":
            len(results),

        "operational":
            sum(
                1
                for item in results
                if item["operativa"]
            ),

        "suspended":
            sum(
                1
                for item in results
                if not item["operativa"]
            ),

        "external_errors":
            sum(
                item[
                    "external_errors"
                ]
                for item in results
            ),

        "results":
            results,

        "dry_run":
            bool(dry_run),
    }


def desactivar_empresa_admin(
    empresa_id: int,
) -> dict:
    """
    Suspensión administrativa reversible.
    """

    from django.db import transaction

    from core.models import Empresa

    with transaction.atomic():

        empresa = (
            Empresa.objects
            .select_for_update()
            .get(
                pk=empresa_id
            )
        )

        if (
            empresa.estado
            !=
            Empresa.Estado.SUSPENDIDA
        ):

            empresa.estado = (
                Empresa.Estado.SUSPENDIDA
            )

            empresa.save(
                update_fields=[
                    "estado",
                    "actualizado_en",
                ]
            )

    sesiones = (
        cerrar_sesiones_empresa(
            empresa_id
        )
    )

    whatsapp = (
        _sincronizar_whatsapp_empresa(
            empresa_id,
            habilitar=False,
            dry_run=False,
            strict=False,
        )
    )

    return {
        "empresa_id":
            empresa_id,

        "sessions_closed":
            sesiones,

        "external_errors":
            len(
                whatsapp["errors"]
            ),

        "whatsapp":
            whatsapp,
    }


def reactivar_empresa_admin(
    empresa_id: int,
) -> dict:
    """
    Reactivación manual.

    Exige licencia vigente.
    WhatsApp se habilita ANTES de cambiar
    Empresa a activa. Si falla, la empresa
    permanece suspendida.
    """

    from django.db import transaction

    from core.models import Empresa

    empresa = (
        Empresa.objects
        .get(
            pk=empresa_id
        )
    )

    if not licencia_vigente_empresa(
        empresa
    ):
        raise LicenciaNoVigenteError(
            "La empresa no tiene una "
            "licencia activa y vigente."
        )

    whatsapp = (
        _sincronizar_whatsapp_empresa(
            empresa_id,
            habilitar=True,
            dry_run=False,
            strict=True,
        )
    )

    with transaction.atomic():

        locked = (
            Empresa.objects
            .select_for_update()
            .get(
                pk=empresa_id
            )
        )

        locked.estado = (
            Empresa.Estado.ACTIVA
        )

        locked.save(
            update_fields=[
                "estado",
                "actualizado_en",
            ]
        )

    return {
        "empresa_id":
            empresa_id,

        "external_errors":
            0,

        "whatsapp":
            whatsapp,
    }
