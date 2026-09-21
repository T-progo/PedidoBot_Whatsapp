"""
Restablecimiento controlado de conexiones externas.

TNL-CLIENT-CONNECTION-RESET-SERVICE-V1

Destruye únicamente material reutilizable de conexión:

- Instancia/sesión Evolution WhatsApp.
- Configuración OAuth Mercado Pago.
- Configuración OAuth Google Calendar.
- Estados OAuth transitorios en sesiones Django.

Conserva:
Empresa, usuarios, licencia, instalación, Bot, Typebot,
plantillas, catálogo, pedidos, pagos, citas, agenda,
horarios, IA, bolsas, consumos y aceptación de términos.
"""

from __future__ import annotations

import re

from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import transaction


INSTANCE_RE = re.compile(
    r"^tnl-e[0-9]+-i[0-9]+$"
)


class ConnectionResetError(
    RuntimeError
):
    pass


def _expected_instance_for_channel(
    canal,
) -> str:

    from core.models import (
        InstalacionPlantilla,
    )

    if (
        canal.bot_id is None
        or
        canal.bot.plantilla_id is None
    ):
        return ""

    instalacion = (
        InstalacionPlantilla.objects
        .filter(
            empresa_id=
                canal.bot.empresa_id,
            plantilla_id=
                canal.bot.plantilla_id,
        )
        .order_by("-id")
        .first()
    )

    if instalacion is None:
        return ""

    return (
        f"tnl-e{canal.bot.empresa_id}"
        f"-i{instalacion.id}"
    )


def _resolver_instance_channel(
    canal,
) -> str:

    actual = str(
        canal.identificador
        or ""
    ).strip()

    expected = (
        _expected_instance_for_channel(
            canal
        )
    )


    if actual:

        if not INSTANCE_RE.fullmatch(
            actual
        ):
            raise ConnectionResetError(
                "El canal WhatsApp contiene "
                "un identificador técnico "
                "no administrado por "
                "NegocioListo."
            )


        if (
            expected
            and
            actual != expected
        ):
            raise ConnectionResetError(
                "El identificador WhatsApp "
                "no coincide con la "
                "instalación de la empresa."
            )

        return actual


    if (
        expected
        and
        INSTANCE_RE.fullmatch(
            expected
        )
    ):
        return expected


    return ""


def plan_restablecer_conexiones(
    empresa,
) -> dict:

    from core.models import (
        Canal,
        ConfiguracionMercadoPago,
        ConfiguracionGoogleCalendar,
        Pedido,
        Pago,
        Cita,
        Catalogo,
        Producto,
        ConfiguracionAgenda,
        HorarioAtencion,
    )

    canales = list(
        Canal.objects
        .filter(
            bot__empresa=empresa,
            tipo="whatsapp",
        )
        .select_related(
            "bot",
            "bot__empresa",
            "bot__plantilla",
        )
        .order_by("id")
    )


    instances = []

    for canal in canales:

        instance = (
            _resolver_instance_channel(
                canal
            )
        )

        if instance:
            instances.append(
                instance
            )


    return {
        "empresa_id":
            empresa.id,

        "whatsapp_channels":
            len(canales),

        "whatsapp_instances":
            len(
                set(
                    instances
                )
            ),

        "mercadopago_config":
            ConfiguracionMercadoPago
            .objects
            .filter(
                empresa=empresa
            )
            .exists(),

        "google_config":
            ConfiguracionGoogleCalendar
            .objects
            .filter(
                empresa=empresa
            )
            .exists(),

        "historical": {
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

            "catalogos":
                Catalogo.objects
                .filter(
                    empresa=empresa
                )
                .count(),

            "productos":
                Producto.objects
                .filter(
                    catalogo__empresa=
                        empresa
                )
                .count(),

            "agenda":
                ConfiguracionAgenda
                .objects
                .filter(
                    empresa=empresa
                )
                .count(),

            "horarios":
                HorarioAtencion
                .objects
                .filter(
                    empresa=empresa
                )
                .count(),
        },
    }


_MP_KEYS = (
    "tnl_mercadopago_oauth_state",
    "tnl_mercadopago_oauth_empresa_id",
    "tnl_mercadopago_oauth_issued_at",
    "tnl_mercadopago_oauth_code_verifier",
)

_GC_KEYS = (
    "tnl_google_calendar_oauth_state",
    "tnl_google_calendar_oauth_empresa_id",
    "tnl_google_calendar_oauth_issued_at",
    "tnl_google_calendar_oauth_code_verifier",
    "tnl_google_calendar_oauth_user_id",
    "tnl_google_calendar_oauth_origen",
)


def _int_equal(
    value,
    expected,
) -> bool:

    try:
        return int(value) == int(expected)

    except (
        TypeError,
        ValueError,
    ):
        return False


def limpiar_sesiones_oauth_empresa(
    empresa_id: int,
) -> int:
    """
    Retira states/PKCE antiguos para impedir
    que un callback iniciado antes del reset
    vuelva a guardar una conexión vieja.

    NO cierra la sesión de login.
    """

    from importlib import import_module

    engine = import_module(
        settings.SESSION_ENGINE
    )

    Store = engine.SessionStore

    changed_sessions = 0


    for row in (
        Session.objects
        .all()
        .iterator()
    ):

        store = Store(
            session_key=
                row.session_key
        )

        try:

            data = dict(
                store.items()
            )

        except Exception:
            continue


        clear_mp = _int_equal(
            data.get(
                "tnl_mercadopago_oauth_empresa_id"
            ),
            empresa_id,
        )

        clear_gc = _int_equal(
            data.get(
                "tnl_google_calendar_oauth_empresa_id"
            ),
            empresa_id,
        )


        if not (
            clear_mp
            or
            clear_gc
        ):
            continue


        if clear_mp:

            for key in _MP_KEYS:

                store.pop(
                    key,
                    None,
                )


        if clear_gc:

            for key in _GC_KEYS:

                store.pop(
                    key,
                    None,
                )


        store.save(
            must_create=False
        )

        changed_sessions += 1


    return changed_sessions


def restablecer_conexiones_empresa(
    empresa_id: int,
    *,
    dry_run: bool = False,
) -> dict:

    from core.models import (
        Empresa,
        Canal,
        ConfiguracionMercadoPago,
        ConfiguracionGoogleCalendar,
    )

    from core.integrations.evolution_client import (
        EvolutionClient,
        EvolutionClientError,
    )


    empresa = (
        Empresa.objects
        .get(
            pk=empresa_id
        )
    )


    plan = (
        plan_restablecer_conexiones(
            empresa
        )
    )


    if dry_run:

        return {
            **plan,
            "dry_run":
                True,

            "evolution_deleted":
                0,

            "oauth_sessions_cleaned":
                0,
        }


    canales = list(
        Canal.objects
        .filter(
            bot__empresa=empresa,
            tipo="whatsapp",
        )
        .select_related(
            "bot",
            "bot__empresa",
            "bot__plantilla",
        )
        .order_by("id")
    )


    instance_names = []

    for canal in canales:

        instance = (
            _resolver_instance_channel(
                canal
            )
        )

        if instance:

            instance_names.append(
                instance
            )


    instance_names = sorted(
        set(
            instance_names
        )
    )


    #
    # Primero Evolution.
    #
    # No tocamos BD mientras no sepamos que
    # cada recurso remoto pudo eliminarse
    # o ya estaba ausente.
    #
    evolution = EvolutionClient()

    evolution_deleted = 0


    for instance in instance_names:

        try:

            before = (
                evolution.find_instance(
                    instance
                )
            )


            if before is None:
                continue


            evolution.delete_instance(
                instance
            )


            #
            # TNL-EVOLUTION-DELETE-POLL-V1
            #
            # Evolution puede mantener la
            # instancia visible durante unos
            # segundos después de DELETE.
            #
            # No considerar ese estado
            # transitorio como un fallo.
            #
            import time

            after = None

            for _attempt in range(30):

                after = (
                    evolution.find_instance(
                        instance
                    )
                )

                if after is None:
                    break

                time.sleep(0.5)


            if after is not None:

                raise ConnectionResetError(
                    "Evolution continúa "
                    "reportando la instancia "
                    "15 segundos después "
                    "de eliminarla."
                )


            evolution_deleted += 1


        except ConnectionResetError:
            raise


        except EvolutionClientError as exc:

            #
            # Carrera segura:
            # si otro proceso ya la eliminó,
            # la ausencia final equivale a éxito.
            #
            try:

                final = (
                    evolution.find_instance(
                        instance
                    )
                )

            except Exception:

                final = "UNKNOWN"


            if final is None:
                continue


            raise ConnectionResetError(
                "No fue posible eliminar "
                "completamente la conexión "
                "WhatsApp."
            ) from exc


    #
    # Sólo después limpiamos la persistencia
    # local de conexión.
    #
    with transaction.atomic():

        canal_ids = [
            canal.id
            for canal in canales
        ]


        locked = (
            Canal.objects
            .select_for_update()
            .filter(
                id__in=canal_ids
            )
        )


        for canal in locked:

            canal.activo = False

            canal.identificador = ""

            canal.save(
                update_fields=[
                    "activo",
                    "identificador",
                    "actualizado_en",
                ]
            )


        mp_deleted = (
            ConfiguracionMercadoPago
            .objects
            .filter(
                empresa_id=empresa_id
            )
            .delete()[0]
        )


        gc_deleted = (
            ConfiguracionGoogleCalendar
            .objects
            .filter(
                empresa_id=empresa_id
            )
            .delete()[0]
        )


    oauth_sessions = (
        limpiar_sesiones_oauth_empresa(
            empresa_id
        )
    )


    #
    # Verificación posterior local.
    #
    if (
        ConfiguracionMercadoPago
        .objects
        .filter(
            empresa_id=empresa_id
        )
        .exists()
    ):

        raise ConnectionResetError(
            "Mercado Pago no quedó limpio."
        )


    if (
        ConfiguracionGoogleCalendar
        .objects
        .filter(
            empresa_id=empresa_id
        )
        .exists()
    ):

        raise ConnectionResetError(
            "Google Calendar no quedó limpio."
        )


    for canal in (
        Canal.objects
        .filter(
            bot__empresa_id=
                empresa_id,
            tipo="whatsapp",
        )
    ):

        if canal.activo:

            raise ConnectionResetError(
                "Un Canal WhatsApp quedó activo."
            )

        if str(
            canal.identificador
            or ""
        ).strip():

            raise ConnectionResetError(
                "Un Canal WhatsApp conservó "
                "su identificador técnico."
            )


    return {
        **plan,

        "dry_run":
            False,

        "evolution_deleted":
            evolution_deleted,

        "mercadopago_deleted":
            int(
                mp_deleted
                > 0
            ),

        "google_deleted":
            int(
                gc_deleted
                > 0
            ),

        "oauth_sessions_cleaned":
            oauth_sessions,
    }
