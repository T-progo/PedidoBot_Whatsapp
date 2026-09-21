from __future__ import annotations

import json
from pathlib import Path


# TNL-IA-REDIS-MEMORY-V1

IA_MEMORY_TTL_SECONDS = 3600
IA_MEMORY_MAX_EXCHANGES = 6
IA_MEMORY_MAX_MESSAGES = (
    IA_MEMORY_MAX_EXCHANGES
    * 2
)

IA_MEMORY_MAX_CONTENT_CHARS = 4000

_REDIS_HOST = "127.0.0.1"
_REDIS_PORT = 6379
_REDIS_DB = 0

_REDIS_USERNAME = "ia_context"

_REDIS_PASSWORD_FILE = Path(
    "/opt/tunegociolisto/"
    "infrastructure/secrets/"
    "ia_context_redis_password"
)

_KEY_PREFIX = "tnl:ia:ctx:"


def _leer_password_redis() -> str:
    """
    Lee la credencial dedicada sin exponerla.
    """

    try:

        stat_result = (
            _REDIS_PASSWORD_FILE.stat()
        )

        if (
            stat_result.st_mode
            & 0o077
        ):
            return ""

        password = (
            _REDIS_PASSWORD_FILE
            .read_text(
                encoding="utf-8"
            )
            .strip()
        )

    except (
        OSError,
        UnicodeError,
    ):
        return ""

    if not password:
        return ""

    if len(password) > 512:
        return ""

    return password


def _clave_contexto(
    referencia_conversacion,
) -> str:
    """
    Construye únicamente claves del namespace ACL
    autorizado.

    La referencia ya debe venir pseudonimizada.
    """

    from core.services.ia_contexto import (
        referencia_typebot_valida,
    )

    referencia = str(
        referencia_conversacion
        or ""
    ).strip()

    if not referencia_typebot_valida(
        referencia
    ):
        return ""

    return (
        _KEY_PREFIX
        +
        referencia
    )


def _crear_cliente_redis():
    """
    Cliente corto con timeouts estrictos.

    Cualquier excepción debe ser tratada por los
    consumidores como degradación a modo stateless.
    """

    import redis

    password = (
        _leer_password_redis()
    )

    if not password:
        raise RuntimeError(
            "Credencial Redis IA no disponible."
        )

    return redis.Redis(
        host=_REDIS_HOST,
        port=_REDIS_PORT,
        db=_REDIS_DB,
        username=
            _REDIS_USERNAME,
        password=password,
        decode_responses=True,
        socket_connect_timeout=0.75,
        socket_timeout=0.75,
        health_check_interval=30,
    )


def _normalizar_contenido(
    value,
) -> str:
    """
    Normalización defensiva del contenido guardado.
    """

    value = str(
        value
        or ""
    ).strip()

    if not value:
        return ""

    if len(value) > (
        IA_MEMORY_MAX_CONTENT_CHARS
    ):
        value = value[
            :IA_MEMORY_MAX_CONTENT_CHARS
        ].rstrip()

    return value


def obtener_historial(
    referencia_conversacion,
) -> list[dict]:
    """
    Obtiene máximo los últimos seis intercambios.

    Fail-open:
    si Redis no está disponible retorna [].
    """

    key = _clave_contexto(
        referencia_conversacion
    )

    if not key:
        return []

    try:

        client = (
            _crear_cliente_redis()
        )

        raw_items = client.lrange(
            key,
            -IA_MEMORY_MAX_MESSAGES,
            -1,
        )

    except Exception:

        return []

    history = []

    for raw in raw_items:

        try:

            item = json.loads(
                raw
            )

        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            continue

        if not isinstance(
            item,
            dict,
        ):
            continue

        role = str(
            item.get(
                "role"
            )
            or ""
        ).strip()

        if role not in {
            "user",
            "assistant",
        }:
            continue

        content = (
            _normalizar_contenido(
                item.get(
                    "content"
                )
            )
        )

        if not content:
            continue

        history.append(
            {
                "role":
                    role,

                "content":
                    content,
            }
        )

    if len(history) > (
        IA_MEMORY_MAX_MESSAGES
    ):
        history = history[
            -IA_MEMORY_MAX_MESSAGES:
        ]

    return history


def guardar_intercambio(
    referencia_conversacion,
    *,
    mensaje_usuario,
    respuesta_asistente,
) -> bool:
    """
    Guarda usuario + asistente en una sola transacción
    Redis.

    La lista queda limitada a 12 mensajes y el TTL
    vuelve a 3600 segundos después de cada respuesta
    exitosa.

    Fail-open:
    cualquier error devuelve False.
    """

    key = _clave_contexto(
        referencia_conversacion
    )

    if not key:
        return False

    user_content = (
        _normalizar_contenido(
            mensaje_usuario
        )
    )

    assistant_content = (
        _normalizar_contenido(
            respuesta_asistente
        )
    )

    if (
        not user_content
        or
        not assistant_content
    ):
        return False

    user_item = json.dumps(
        {
            "role":
                "user",

            "content":
                user_content,
        },
        ensure_ascii=False,
        separators=(
            ",",
            ":",
        ),
    )

    assistant_item = json.dumps(
        {
            "role":
                "assistant",

            "content":
                assistant_content,
        },
        ensure_ascii=False,
        separators=(
            ",",
            ":",
        ),
    )

    try:

        client = (
            _crear_cliente_redis()
        )

        pipe = client.pipeline(
            transaction=True
        )

        pipe.rpush(
            key,
            user_item,
            assistant_item,
        )

        pipe.ltrim(
            key,
            -IA_MEMORY_MAX_MESSAGES,
            -1,
        )

        pipe.expire(
            key,
            IA_MEMORY_TTL_SECONDS,
        )

        result = pipe.execute()

        if (
            not isinstance(
                result,
                list,
            )
            or
            len(result) != 3
        ):
            return False

    except Exception:

        return False

    return True


def borrar_historial(
    referencia_conversacion,
) -> bool:
    """
    Elimina únicamente una clave válida del namespace IA.

    Principalmente útil para pruebas y futuros controles
    operativos.
    """

    key = _clave_contexto(
        referencia_conversacion
    )

    if not key:
        return False

    try:

        client = (
            _crear_cliente_redis()
        )

        client.delete(
            key
        )

    except Exception:

        return False

    return True
