"""
OAuth Google Calendar para NegocioListo.

TNL-GOOGLE-CALENDAR-OAUTH-V1

Responsabilidades:
- credencial OAuth global de la plataforma;
- OAuth individual por empresa;
- scopes mínimos de Calendar;
- cifrado/descifrado de tokens;
- construcción local del flujo OAuth;
- NO realizar llamadas de red al importarse.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet


GOOGLE_CALENDAR_CONFIG_DIR_DEFAULT = (
    "/opt/tunegociolisto/"
    "configs/google-calendar"
)


GOOGLE_CALENDAR_SCOPES = (
    "https://www.googleapis.com/auth/"
    "calendar.calendarlist.readonly",

    "https://www.googleapis.com/auth/"
    "calendar.events",

    "https://www.googleapis.com/auth/"
    "calendar.freebusy",
)


class GoogleCalendarConfiguracionError(
    RuntimeError
):
    """Configuración OAuth Google incompleta."""


def _config_dir() -> Path:

    return Path(
        os.environ.get(
            "TNL_GOOGLE_CALENDAR_CONFIG_DIR",
            GOOGLE_CALENDAR_CONFIG_DIR_DEFAULT,
        )
    )


def _leer(
    nombre: str,
) -> str:

    path = (
        _config_dir()
        /
        nombre
    )


    if not path.is_file():

        return ""


    return (
        path.read_text(
            encoding="utf-8"
        )
        .strip()
    )


def client_id_configurado() -> bool:

    return bool(
        _leer(
            "client_id"
        )
    )


def client_secret_configurado() -> bool:

    return bool(
        _leer(
            "client_secret"
        )
    )


def oauth_configurado() -> bool:

    return bool(
        client_id_configurado()
        and
        client_secret_configurado()
        and
        obtener_redirect_uri()
    )


def obtener_client_id() -> str:

    value = _leer(
        "client_id"
    )


    if not value:

        raise GoogleCalendarConfiguracionError(
            "Google OAuth client_id "
            "no configurado."
        )


    return value


def obtener_client_secret() -> str:

    value = _leer(
        "client_secret"
    )


    if not value:

        raise GoogleCalendarConfiguracionError(
            "Google OAuth client_secret "
            "no configurado."
        )


    return value


def obtener_redirect_uri() -> str:

    value = _leer(
        "redirect_uri"
    )


    if not value:

        raise GoogleCalendarConfiguracionError(
            "Google OAuth redirect_uri "
            "no configurado."
        )


    return value


def _obtener_fernet() -> Fernet:

    value = _leer(
        "fernet.key"
    )


    if not value:

        raise GoogleCalendarConfiguracionError(
            "Clave Fernet de Google Calendar "
            "no configurada."
        )


    try:

        return Fernet(
            value.encode(
                "ascii"
            )
        )

    except Exception as exc:

        raise GoogleCalendarConfiguracionError(
            "Clave Fernet de Google Calendar "
            "inválida."
        ) from exc


def cifrar_token(
    token: str,
) -> str:

    if not token:

        return ""


    return (
        _obtener_fernet()
        .encrypt(
            token.encode(
                "utf-8"
            )
        )
        .decode(
            "ascii"
        )
    )


def descifrar_token(
    token_cifrado: str,
) -> str:

    if not token_cifrado:

        return ""


    return (
        _obtener_fernet()
        .decrypt(
            token_cifrado.encode(
                "ascii"
            )
        )
        .decode(
            "utf-8"
        )
    )


def obtener_client_config() -> dict:

    return {
        "web": {
            "client_id":
                obtener_client_id(),

            "client_secret":
                obtener_client_secret(),

            "auth_uri":
                "https://accounts.google.com/o/oauth2/auth",

            "token_uri":
                "https://oauth2.googleapis.com/token",

            "redirect_uris": [
                obtener_redirect_uri()
            ],
        }
    }


# TNL-GOOGLE-CALENDAR-PKCE-V1
def crear_flujo_oauth(
    *,
    state: Optional[str] = None,
    code_verifier: Optional[str] = None,
    autogenerate_code_verifier: bool = True,
):

    from google_auth_oauthlib.flow import Flow


    flow = Flow.from_client_config(
        obtener_client_config(),
        scopes=list(
            GOOGLE_CALENDAR_SCOPES
        ),
        state=state,
        code_verifier=code_verifier,
        autogenerate_code_verifier=
            autogenerate_code_verifier,
    )


    flow.redirect_uri = (
        obtener_redirect_uri()
    )


    return flow


def generar_url_autorizacion(
    *,
    state: Optional[str] = None,
) -> tuple[str, str, str]:

    flow = crear_flujo_oauth(
        state=state
    )


    authorization_url, generated_state = (
        flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
    )


    code_verifier = (
        flow.code_verifier
        or
        ""
    )


    if not code_verifier:

        raise GoogleCalendarConfiguracionError(
            "Google OAuth no generó "
            "code_verifier PKCE."
        )


    return (
        authorization_url,
        generated_state,
        code_verifier,
    )
