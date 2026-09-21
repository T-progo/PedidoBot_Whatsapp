"""
Integración segura Mercado Pago para NegocioListo.

TNL-MERCADOPAGO-SECURE-SERVICE-V1

Este módulo:
- lee credenciales globales desde archivos privados;
- cifra tokens OAuth por empresa;
- genera state y PKCE S256;
- construye la URL de autorización;
- NO imprime secretos.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import urllib.error
import urllib.request

from pathlib import Path
from urllib.parse import quote, urlencode

from cryptography.fernet import Fernet


MERCADOPAGO_AUTH_URL = (
    "https://auth.mercadopago.com/"
    "authorization"
)

MERCADOPAGO_TOKEN_URL = (
    "https://api.mercadopago.com/"
    "oauth/token"
)


_DEFAULT_CONFIG_DIR = (
    "/opt/tunegociolisto/"
    "configs/mercadopago"
)


def _config_dir() -> Path:

    return Path(
        os.environ.get(
            "TNL_MERCADOPAGO_CONFIG_DIR",
            _DEFAULT_CONFIG_DIR,
        )
    )


def _read_private_file(
    name: str,
    *,
    required: bool = True,
) -> str:

    path = (
        _config_dir()
        / name
    )

    if not path.is_file():

        if required:
            raise RuntimeError(
                "Configuración Mercado Pago "
                "incompleta."
            )

        return ""


    value = (
        path.read_text(
            encoding="utf-8"
        )
        .strip()
    )


    if required and not value:

        raise RuntimeError(
            "Configuración Mercado Pago "
            "incompleta."
        )


    return value


def credenciales_aplicacion_configuradas() -> bool:

    client_id = (
        _read_private_file(
            "client_id",
            required=False,
        )
    )

    client_secret = (
        _read_private_file(
            "client_secret",
            required=False,
        )
    )

    return bool(
        client_id
        and
        client_secret
    )


def obtener_client_id() -> str:

    return _read_private_file(
        "client_id"
    )


def obtener_client_secret() -> str:

    return _read_private_file(
        "client_secret"
    )


def obtener_redirect_uri() -> str:

    return _read_private_file(
        "redirect_uri"
    )


def _fernet() -> Fernet:

    key = (
        _read_private_file(
            "fernet.key"
        )
        .encode(
            "ascii"
        )
    )

    return Fernet(
        key
    )


def cifrar_secreto(
    value: str,
) -> str:

    if not isinstance(
        value,
        str,
    ):

        raise TypeError(
            "El secreto debe ser texto."
        )


    if not value:

        return ""


    return (
        _fernet()
        .encrypt(
            value.encode(
                "utf-8"
            )
        )
        .decode(
            "ascii"
        )
    )


def descifrar_secreto(
    encrypted_value: str,
) -> str:

    if not encrypted_value:

        return ""


    return (
        _fernet()
        .decrypt(
            encrypted_value.encode(
                "ascii"
            )
        )
        .decode(
            "utf-8"
        )
    )


def generar_estado_oauth() -> str:

    return secrets.token_urlsafe(
        32
    )


def generar_pkce() -> tuple[str, str]:

    verifier = (
        secrets.token_urlsafe(
            64
        )
    )


    digest = (
        hashlib.sha256(
            verifier.encode(
                "ascii"
            )
        )
        .digest()
    )


    challenge = (
        base64.urlsafe_b64encode(
            digest
        )
        .rstrip(b"=")
        .decode(
            "ascii"
        )
    )


    return (
        verifier,
        challenge,
    )


def construir_url_autorizacion(
    *,
    state: str,
    code_challenge: str,
) -> str:

    if not state:
        raise ValueError(
            "state es obligatorio."
        )


    if not code_challenge:
        raise ValueError(
            "code_challenge "
            "es obligatorio."
        )


    params = {
        "client_id":
            obtener_client_id(),

        "response_type":
            "code",

        "state":
            state,

        "redirect_uri":
            obtener_redirect_uri(),

        "code_challenge":
            code_challenge,

        "code_challenge_method":
            "S256",
    }


    return (
        MERCADOPAGO_AUTH_URL
        + "?"
        + urlencode(
            params
        )
    )


# =============================================================================
# TNL-MERCADOPAGO-OAUTH-EXCHANGE-V1
# Intercambio seguro authorization_code -> tokens.
# =============================================================================

class MercadoPagoOAuthError(
    RuntimeError
):
    """
    Error seguro de integración OAuth.

    Nunca debe contener tokens, códigos,
    Client Secret ni cuerpo de respuesta.
    """
    pass


def oauth_configurado() -> bool:

    try:

        if not credenciales_aplicacion_configuradas():
            return False

        if not obtener_redirect_uri():
            return False

        key = _read_private_file(
            "fernet.key",
            required=False,
        )

        if not key:
            return False

        # También valida que la llave Fernet sea utilizable.
        _fernet()

        return True

    except Exception:
        return False


def intercambiar_codigo_oauth(
    *,
    code: str,
    code_verifier: str,
) -> dict:

    code = str(
        code
        or ""
    ).strip()

    code_verifier = str(
        code_verifier
        or ""
    ).strip()

    if not code:
        raise MercadoPagoOAuthError(
            "Código OAuth ausente."
        )

    if not (
        43
        <= len(code_verifier)
        <= 128
    ):
        raise MercadoPagoOAuthError(
            "PKCE inválido."
        )

    payload = {
        "client_id":
            obtener_client_id(),

        "client_secret":
            obtener_client_secret(),

        "grant_type":
            "authorization_code",

        "code":
            code,

        "redirect_uri":
            obtener_redirect_uri(),

        "code_verifier":
            code_verifier,
    }

    request = urllib.request.Request(
        MERCADOPAGO_TOKEN_URL,
        data=json.dumps(
            payload
        ).encode(
            "utf-8"
        ),
        headers={
            "Content-Type":
                "application/json",

            "Accept":
                "application/json",
        },
        method="POST",
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=20,
        ) as response:

            raw = response.read()

    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
    ) as exc:

        raise MercadoPagoOAuthError(
            "No fue posible intercambiar "
            "el código OAuth."
        ) from exc

    try:

        data = json.loads(
            raw.decode(
                "utf-8"
            )
        )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:

        raise MercadoPagoOAuthError(
            "Respuesta OAuth inválida."
        ) from exc

    if not isinstance(
        data,
        dict,
    ):
        raise MercadoPagoOAuthError(
            "Respuesta OAuth inválida."
        )

    return data


# =============================================================================
# TNL-MERCADOPAGO-WEBHOOK-SERVICE-V1
# Firma Webhook + consulta segura API.
# =============================================================================

MERCADOPAGO_API_BASE = (
    "https://api.mercadopago.com"
)


class MercadoPagoAPIError(
    RuntimeError
):
    """
    Error seguro de comunicación con Mercado Pago.

    No debe contener Access Token,
    cuerpo remoto ni credenciales.
    """
    pass


def obtener_webhook_secret() -> str:

    return _read_private_file(
        "webhook_secret"
    )


def validar_firma_webhook(
    *,
    x_signature: str,
    x_request_id: str,
    data_id: str,
) -> bool:
    """
    Valida x-signature según el manifiesto
    documentado por Mercado Pago:

    id:<data.id>;request-id:<request-id>;ts:<ts>;

    Los componentes ausentes se omiten.
    """

    x_signature = str(
        x_signature
        or ""
    ).strip()

    x_request_id = str(
        x_request_id
        or ""
    ).strip()

    data_id = str(
        data_id
        or ""
    ).strip()

    if not x_signature:
        return False

    ts = ""
    signature_v1 = ""

    for part in x_signature.split(","):

        key_value = part.split(
            "=",
            1,
        )

        if len(key_value) != 2:
            continue

        key = key_value[0].strip()
        value = key_value[1].strip()

        if key == "ts":
            ts = value

        elif key == "v1":
            signature_v1 = value

    if not ts or not signature_v1:
        return False

    manifest_parts = []

    if data_id:

        # Mercado Pago indica lowercase para
        # IDs alfanuméricos en el manifiesto.
        manifest_parts.append(
            "id:"
            +
            data_id.lower()
            +
            ";"
        )

    if x_request_id:

        manifest_parts.append(
            "request-id:"
            +
            x_request_id
            +
            ";"
        )

    if ts:

        manifest_parts.append(
            "ts:"
            +
            ts
            +
            ";"
        )

    manifest = "".join(
        manifest_parts
    )

    try:

        secret = obtener_webhook_secret()

        expected = hmac.new(
            secret.encode(
                "utf-8"
            ),
            manifest.encode(
                "utf-8"
            ),
            hashlib.sha256,
        ).hexdigest()

    except Exception:
        return False

    return hmac.compare_digest(
        expected.lower(),
        signature_v1.lower(),
    )


def _mercadopago_api_json(
    *,
    method: str,
    path: str,
    access_token: str,
    payload=None,
) -> dict:

    method = str(
        method
        or ""
    ).upper().strip()

    path = str(
        path
        or ""
    ).strip()

    access_token = str(
        access_token
        or ""
    ).strip()

    if method not in {
        "GET",
        "POST",
        "PUT",
    }:
        raise MercadoPagoAPIError(
            "Método API inválido."
        )

    if (
        not path
        or
        not path.startswith("/")
        or
        path.startswith("//")
    ):
        raise MercadoPagoAPIError(
            "Ruta API inválida."
        )

    if not access_token:
        raise MercadoPagoAPIError(
            "Access Token ausente."
        )

    headers = {
        "Authorization":
            "Bearer "
            +
            access_token,

        "Accept":
            "application/json",
    }

    body = None

    if payload is not None:

        headers[
            "Content-Type"
        ] = "application/json"

        body = json.dumps(
            payload,
            separators=(
                ",",
                ":",
            ),
        ).encode(
            "utf-8"
        )

    request = urllib.request.Request(
        MERCADOPAGO_API_BASE
        +
        path,
        data=body,
        headers=headers,
        method=method,
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=20,
        ) as response:

            raw = response.read()

    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
    ) as exc:

        raise MercadoPagoAPIError(
            "Mercado Pago API no respondió "
            "correctamente."
        ) from exc

    try:

        data = json.loads(
            raw.decode(
                "utf-8"
            )
        )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:

        raise MercadoPagoAPIError(
            "Respuesta Mercado Pago inválida."
        ) from exc

    if not isinstance(
        data,
        dict,
    ):
        raise MercadoPagoAPIError(
            "Respuesta Mercado Pago inválida."
        )

    return data


def consultar_pago_mercadopago(
    *,
    access_token: str,
    payment_id: str,
) -> dict:

    payment_id = str(
        payment_id
        or ""
    ).strip()

    if not payment_id:
        raise MercadoPagoAPIError(
            "Payment ID ausente."
        )

    return _mercadopago_api_json(
        method="GET",
        path=(
            "/v1/payments/"
            +
            quote(
                payment_id,
                safe="",
            )
        ),
        access_token=
            access_token,
    )


# =============================================================================
# TNL-MERCADOPAGO-CHECKOUT-PREFERENCE-V1
# Creación de preferencia Checkout Pro.
# =============================================================================

MERCADOPAGO_WEBHOOK_URL = (
    "https://admin.negociolisto.com.mx/"
    "mercado-pago/webhook/"
    "?source_news=webhooks"
)


def crear_preferencia_checkout_pro(
    *,
    access_token: str,
    external_reference: str,
    pedido_numero: str,
    monto,
    moneda: str,
    expected_collector_id: str,
    titulo_item: str = "",
    expiration_date_from: str = "",
    expiration_date_to: str = "",
) -> dict:

    from decimal import (
        Decimal,
        InvalidOperation,
    )

    from urllib.parse import (
        quote,
        urlsplit,
    )

    access_token = str(
        access_token
        or ""
    ).strip()

    external_reference = str(
        external_reference
        or ""
    ).strip()

    pedido_numero = str(
        pedido_numero
        or ""
    ).strip()

    moneda = str(
        moneda
        or ""
    ).strip().upper()

    expected_collector_id = str(
        expected_collector_id
        or ""
    ).strip()

    if not access_token:
        raise MercadoPagoAPIError(
            "Access Token ausente."
        )

    if not external_reference:
        raise MercadoPagoAPIError(
            "Referencia externa ausente."
        )

    if not pedido_numero:
        raise MercadoPagoAPIError(
            "Número de pedido ausente."
        )

    if not moneda:
        raise MercadoPagoAPIError(
            "Moneda ausente."
        )

    if not expected_collector_id:
        raise MercadoPagoAPIError(
            "Collector esperado ausente."
        )

    try:

        amount = Decimal(
            str(
                monto
            )
        )

    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ) as exc:

        raise MercadoPagoAPIError(
            "Monto inválido."
        ) from exc

    if amount <= 0:

        raise MercadoPagoAPIError(
            "El monto debe ser mayor que cero."
        )

    amount_2 = amount.quantize(
        Decimal(
            "0.01"
        )
    )

    # No redondear silenciosamente importes
    # de pedidos que excedan la precisión
    # monetaria soportada por Pago.
    if amount != amount_2:

        raise MercadoPagoAPIError(
            "El monto tiene precisión "
            "monetaria incompatible."
        )

    # TNL-MP-PREFERENCE-EXPIRATION-V1
    titulo_item = str(titulo_item or "").strip()
    expiration_date_from = str(expiration_date_from or "").strip()
    expiration_date_to = str(expiration_date_to or "").strip()

    if bool(expiration_date_from) != bool(expiration_date_to):
        raise MercadoPagoAPIError(
            "La vigencia de la preferencia está incompleta."
        )

    payload = {
        "items": [
            {
                "id":
                    pedido_numero[
                        :64
                    ],

                "title":
                    (
                        titulo_item
                        or
                        (
                            "Pedido "
                            +
                            pedido_numero
                        )
                    )[:256],

                "quantity":
                    1,

                "currency_id":
                    moneda,

                "unit_price":
                    float(
                        amount_2
                    ),
            }
        ],

        "external_reference":
            external_reference,

        # Fuerza Webhooks en lugar del
        # mecanismo IPN legado.
        "notification_url":
            MERCADOPAGO_WEBHOOK_URL,
    }

    if expiration_date_from and expiration_date_to:
        payload["expires"] = True
        payload["expiration_date_from"] = expiration_date_from
        payload["expiration_date_to"] = expiration_date_to

    data = _mercadopago_api_json(
        method="POST",
        path="/checkout/preferences",
        access_token=
            access_token,
        payload=payload,
    )

    preference_id = str(
        data.get(
            "id"
        )
        or ""
    ).strip()

    init_point = str(
        data.get(
            "init_point"
        )
        or ""
    ).strip()

    collector_id = str(
        data.get(
            "collector_id"
        )
        or ""
    ).strip()

    # TNL-MP-PREFERENCE-DETAIL-RECOVERY-V1
    #
    # Mercado Pago puede haber creado correctamente
    # la Preference aunque la respuesta inmediata
    # no contenga todavía todos los datos que
    # necesitamos para persistir el checkout.
    #
    # Si ya tenemos preference_id, recuperamos
    # exclusivamente ESA misma Preference por ID.
    # Nunca creamos una segunda Preference aquí.
    if (
        preference_id
        and
        (
            not init_point
            or
            not collector_id
            or
            collector_id
            !=
            expected_collector_id
        )
    ):

        detalle = _mercadopago_api_json(
            method="GET",
            path=(
                "/checkout/preferences/"
                +
                quote(
                    preference_id,
                    safe="",
                )
            ),
            access_token=
                access_token,
        )

        detalle_id = str(
            detalle.get(
                "id"
            )
            or ""
        ).strip()

        if (
            detalle_id
            and
            detalle_id
            ==
            preference_id
        ):

            init_point = str(
                detalle.get(
                    "init_point"
                )
                or
                init_point
                or
                ""
            ).strip()

            collector_id = str(
                detalle.get(
                    "collector_id"
                )
                or
                collector_id
                or
                ""
            ).strip()

    if not preference_id:

        raise MercadoPagoAPIError(
            "Preference ID ausente."
        )

    if not init_point:

        raise MercadoPagoAPIError(
            "Checkout URL ausente."
        )

    parsed = urlsplit(
        init_point
    )

    hostname = str(
        parsed.hostname
        or ""
    ).lower()

    if (
        parsed.scheme
        !=
        "https"
        or
        "mercadopago"
        not in hostname
    ):

        raise MercadoPagoAPIError(
            "Checkout URL inválida."
        )

    if (
        not collector_id
        or
        collector_id
        !=
        expected_collector_id
    ):

        raise MercadoPagoAPIError(
            "Collector inesperado."
        )

    return {
        "preference_id":
            preference_id,

        "checkout_url":
            init_point,

        "collector_id":
            collector_id,
    }


# =============================================================================
# TNL-MERCADOPAGO-OAUTH-REFRESH-V1
# Renovación automática de Access Token OAuth por empresa.
# =============================================================================

def intercambiar_refresh_token(
    *,
    refresh_token: str,
) -> dict:

    refresh_token = str(
        refresh_token
        or ""
    ).strip()

    if not refresh_token:

        raise MercadoPagoOAuthError(
            "Refresh Token ausente."
        )

    payload = {
        "client_id":
            obtener_client_id(),

        "client_secret":
            obtener_client_secret(),

        "grant_type":
            "refresh_token",

        "refresh_token":
            refresh_token,
    }

    request = urllib.request.Request(
        MERCADOPAGO_TOKEN_URL,
        data=json.dumps(
            payload
        ).encode(
            "utf-8"
        ),
        headers={
            "Content-Type":
                "application/json",

            "Accept":
                "application/json",
        },
        method="POST",
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=20,
        ) as response:

            raw = response.read()

    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
    ) as exc:

        raise MercadoPagoOAuthError(
            "No fue posible renovar "
            "la autorización OAuth."
        ) from exc

    try:

        data = json.loads(
            raw.decode(
                "utf-8"
            )
        )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:

        raise MercadoPagoOAuthError(
            "Respuesta de renovación "
            "OAuth inválida."
        ) from exc

    if not isinstance(
        data,
        dict,
    ):

        raise MercadoPagoOAuthError(
            "Respuesta de renovación "
            "OAuth inválida."
        )

    return data


def obtener_access_token_configuracion(
    config_id: int,
    *,
    margen_segundos: int = 300,
) -> str:
    """
    Devuelve un Access Token válido.

    Si el token está próximo a caducar:
    - bloquea la configuración;
    - renueva mediante refresh_token;
    - cifra Access Token nuevo;
    - cifra Refresh Token nuevo;
    - actualiza expiración;
    - nunca muestra secretos.

    La llamada remota de refresh se realiza bajo
    select_for_update deliberadamente: ocurre muy
    pocas veces y evita consumir dos veces un
    refresh_token rotatorio en concurrencia.
    """

    from datetime import (
        timedelta,
    )

    from django.db import (
        transaction,
    )

    from django.utils import (
        timezone,
    )

    from core.models import (
        ConfiguracionMercadoPago,
    )

    try:

        config_id = int(
            config_id
        )

    except (
        TypeError,
        ValueError,
    ) as exc:

        raise MercadoPagoOAuthError(
            "Configuración OAuth inválida."
        ) from exc

    if config_id <= 0:

        raise MercadoPagoOAuthError(
            "Configuración OAuth inválida."
        )

    try:

        margen_segundos = int(
            margen_segundos
        )

    except (
        TypeError,
        ValueError,
    ) as exc:

        raise MercadoPagoOAuthError(
            "Margen OAuth inválido."
        ) from exc

    if (
        margen_segundos < 0
        or
        margen_segundos > 86400
    ):

        raise MercadoPagoOAuthError(
            "Margen OAuth inválido."
        )

    with transaction.atomic():

        config = (
            ConfiguracionMercadoPago.objects
            .select_for_update()
            .get(
                pk=config_id
            )
        )

        if not config.habilitada:

            raise MercadoPagoOAuthError(
                "Mercado Pago no está habilitado."
            )

        if (
            config.estado_conexion
            !=
            ConfiguracionMercadoPago
            .EstadoConexion
            .CONECTADA
        ):

            raise MercadoPagoOAuthError(
                "Mercado Pago no está conectado."
            )

        if not config.access_token_cifrado:

            raise MercadoPagoOAuthError(
                "Access Token no disponible."
            )

        now = timezone.now()

        limite = (
            now
            +
            timedelta(
                seconds=
                    margen_segundos
            )
        )

        # -----------------------------------------------------
        # Token todavía utilizable.
        # -----------------------------------------------------

        if (
            config.token_expira_en
            and
            config.token_expira_en
            >
            limite
        ):

            return descifrar_secreto(
                config.access_token_cifrado
            )

        # -----------------------------------------------------
        # Si no tenemos expiración histórica, no podemos
        # asumir que está vencido. Se conserva el token,
        # pero las conexiones OAuth nuevas sí guardan
        # token_expira_en.
        # -----------------------------------------------------

        if config.token_expira_en is None:

            return descifrar_secreto(
                config.access_token_cifrado
            )

        # -----------------------------------------------------
        # Renovación.
        # -----------------------------------------------------

        if not config.refresh_token_cifrado:

            raise MercadoPagoOAuthError(
                "Refresh Token no disponible. "
                "Se requiere reconectar Mercado Pago."
            )

        refresh_token_actual = (
            descifrar_secreto(
                config.refresh_token_cifrado
            )
        )

        data = intercambiar_refresh_token(
            refresh_token=
                refresh_token_actual
        )

        nuevo_access_token = str(
            data.get(
                "access_token"
            )
            or
            ""
        ).strip()

        nuevo_refresh_token = str(
            data.get(
                "refresh_token"
            )
            or
            ""
        ).strip()

        response_user_id = str(
            data.get(
                "user_id"
            )
            or
            ""
        ).strip()

        expires_in_raw = (
            data.get(
                "expires_in"
            )
        )

        if not nuevo_access_token:

            raise MercadoPagoOAuthError(
                "La renovación no devolvió "
                "Access Token."
            )

        # Mercado Pago rota el Refresh Token.
        # No conservar silenciosamente el anterior.
        if not nuevo_refresh_token:

            raise MercadoPagoOAuthError(
                "La renovación no devolvió "
                "Refresh Token."
            )

        try:

            expires_in = int(
                expires_in_raw
            )

        except (
            TypeError,
            ValueError,
        ) as exc:

            raise MercadoPagoOAuthError(
                "Expiración OAuth inválida."
            ) from exc

        if expires_in <= 0:

            raise MercadoPagoOAuthError(
                "Expiración OAuth inválida."
            )

        # El token renovado debe seguir perteneciendo
        # al mismo vendedor.
        if (
            response_user_id
            and
            config.mp_user_id
            and
            response_user_id
            !=
            str(
                config.mp_user_id
            )
        ):

            raise MercadoPagoOAuthError(
                "La renovación OAuth pertenece "
                "a otro vendedor."
            )

        refreshed_at = (
            timezone.now()
        )

        config.access_token_cifrado = (
            cifrar_secreto(
                nuevo_access_token
            )
        )

        config.refresh_token_cifrado = (
            cifrar_secreto(
                nuevo_refresh_token
            )
        )

        config.token_expira_en = (
            refreshed_at
            +
            timedelta(
                seconds=
                    expires_in
            )
        )

        config.ultima_validacion_en = (
            refreshed_at
        )

        config.ultimo_error = ""

        config.save(
            update_fields=[
                "access_token_cifrado",
                "refresh_token_cifrado",
                "token_expira_en",
                "ultima_validacion_en",
                "ultimo_error",
                "actualizado_en",
            ]
        )

        return nuevo_access_token

