from __future__ import annotations

import hashlib
import hmac
import re

from django.conf import settings


# TNL-IA-CONVERSATION-IDENTITY-V1

_REFERENCE_PREFIX = "wa:v1:"

_INSTANCE_RE = re.compile(
    r"^tnl-e[1-9][0-9]*-i[1-9][0-9]*$"
)

_REMOTE_JID_RE = re.compile(
    r"^[A-Za-z0-9._:+-]+@[A-Za-z0-9.-]+$"
)


def _expected_instance_for_bot(
    bot,
) -> str:
    """
    Resuelve exclusivamente la instancia administrada que
    corresponde al Bot privado.

    No consulta Evolution ni confía en datos recibidos
    desde Typebot.
    """

    if (
        bot is None
        or not getattr(
            bot,
            "pk",
            None,
        )
    ):
        return ""

    empresa_id = getattr(
        bot,
        "empresa_id",
        None,
    )

    if not empresa_id:
        return ""

    plantilla = getattr(
        bot,
        "plantilla",
        None,
    )

    if plantilla is None:
        return ""

    instalacion = getattr(
        plantilla,
        "instalacion_maestra",
        None,
    )

    if instalacion is None:
        return ""

    instalacion_id = getattr(
        instalacion,
        "pk",
        None,
    )

    if not instalacion_id:
        return ""

    return (
        f"tnl-e{int(empresa_id)}"
        f"-i{int(instalacion_id)}"
    )


def _remote_jid_valido(
    remote_jid,
) -> bool:
    """
    Sólo valida forma y tamaño.

    El valor nunca se persiste en claro por este servicio.
    """

    remote_jid = str(
        remote_jid
        or ""
    ).strip()

    if not remote_jid:
        return False

    if len(remote_jid) > 255:
        return False

    if any(
        character.isspace()
        for character in remote_jid
    ):
        return False

    if not _REMOTE_JID_RE.fullmatch(
        remote_jid
    ):
        return False

    return True


def _canal_whatsapp_compatible(
    bot,
    *,
    expected_instance,
) -> bool:
    """
    El Bot debe poseer su Canal WhatsApp.

    El Canal puede estar aún sin identificador durante
    determinadas fases del ciclo de conexión.

    Si ya posee identificador, éste DEBE coincidir con
    la instancia determinista esperada.
    """

    canales = getattr(
        bot,
        "canales",
        None,
    )

    if canales is None:
        return False

    canal = (
        canales
        .filter(
            tipo="whatsapp",
        )
        .only(
            "id",
            "identificador",
        )
        .first()
    )

    if canal is None:
        return False

    identificador = str(
        canal.identificador
        or ""
    ).strip()

    if (
        identificador
        and
        identificador
        != expected_instance
    ):
        return False

    return True


def resolver_referencia_typebot(
    *,
    bot,
    remote_jid,
    instance_name,
) -> str:
    """
    Genera una referencia pseudónima estable para una
    conversación WhatsApp.

    Seguridad:
    - Bot/Empresa vienen de Django.
    - instance_name debe coincidir con la instalación real.
    - remote_jid sólo participa dentro de HMAC-SHA256.
    - jamás se devuelve ni almacena el JID en claro.
    - si cualquier validación falla, retorna cadena vacía
      y el flujo IA puede continuar de forma stateless.
    """

    instance_name = str(
        instance_name
        or ""
    ).strip()

    remote_jid = str(
        remote_jid
        or ""
    ).strip()

    if not instance_name:
        return ""

    if not _INSTANCE_RE.fullmatch(
        instance_name
    ):
        return ""

    if not _remote_jid_valido(
        remote_jid
    ):
        return ""

    expected_instance = (
        _expected_instance_for_bot(
            bot
        )
    )

    if not expected_instance:
        return ""

    if (
        instance_name
        != expected_instance
    ):
        return ""

    if not _canal_whatsapp_compatible(
        bot,
        expected_instance=
            expected_instance,
    ):
        return ""

    empresa_id = int(
        bot.empresa_id
    )

    bot_id = int(
        bot.pk
    )

    canonical = (
        "negociolisto"
        "|conversation-identity"
        "|v1"
        f"|empresa={empresa_id}"
        f"|bot={bot_id}"
        f"|instance={instance_name}"
        f"|remote={remote_jid}"
    )

    secret = str(
        settings.SECRET_KEY
        or ""
    )

    if not secret:
        return ""

    digest = hmac.new(
        secret.encode(
            "utf-8"
        ),
        canonical.encode(
            "utf-8"
        ),
        hashlib.sha256,
    ).hexdigest()

    return (
        _REFERENCE_PREFIX
        +
        digest
    )


def referencia_typebot_valida(
    value,
) -> bool:
    """
    Valida únicamente el formato de una referencia ya
    pseudonimizada.
    """

    value = str(
        value
        or ""
    ).strip()

    if not value.startswith(
        _REFERENCE_PREFIX
    ):
        return False

    digest = value[
        len(
            _REFERENCE_PREFIX
        ):
    ]

    if len(digest) != 64:
        return False

    return all(
        character
        in "0123456789abcdef"
        for character in digest
    )
