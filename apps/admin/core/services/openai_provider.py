"""
Proveedor OpenAI para NegocioListo.

TNL-OPENAI-PROVIDER-V1

Responsabilidades:
- cargar la credencial global desde almacenamiento privado;
- crear el cliente oficial OpenAI;
- definir el modelo recomendado inicial;
- extraer métricas técnicas de uso;
- NO controlar la bolsa comercial;
- NO realizar llamadas de red al importarse.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


OPENAI_MODEL_DEFAULT = "gpt-5.6-luna"

OPENAI_CONFIG_DIR_DEFAULT = (
    "/opt/tunegociolisto/"
    "configs/openai"
)


class OpenAIConfiguracionError(RuntimeError):
    """Configuración local OpenAI incompleta."""


def _config_dir() -> Path:

    return Path(
        os.environ.get(
            "TNL_OPENAI_CONFIG_DIR",
            OPENAI_CONFIG_DIR_DEFAULT,
        )
    )


def _api_key_file() -> Path:

    return (
        _config_dir()
        / "api_key"
    )


def api_key_configurada() -> bool:

    path = _api_key_file()

    if not path.is_file():

        return False


    return bool(
        path.read_text(
            encoding="utf-8"
        )
        .strip()
    )


def obtener_api_key() -> str:

    path = _api_key_file()


    if not path.is_file():

        raise OpenAIConfiguracionError(
            "Credencial OpenAI no configurada."
        )


    value = (
        path.read_text(
            encoding="utf-8"
        )
        .strip()
    )


    if not value:

        raise OpenAIConfiguracionError(
            "Credencial OpenAI no configurada."
        )


    return value


def crear_cliente():

    from openai import OpenAI


    return OpenAI(
        api_key=obtener_api_key()
    )


def extraer_uso(
    response: Any,
) -> dict:
    """
    Extrae métricas técnicas de Responses API.

    No altera el control comercial de palabras.
    """

    usage = getattr(
        response,
        "usage",
        None,
    )


    if usage is None:

        return {
            "tokens_entrada": 0,
            "tokens_salida": 0,
            "tokens_total": 0,
        }


    input_tokens = int(
        getattr(
            usage,
            "input_tokens",
            0,
        )
        or 0
    )


    output_tokens = int(
        getattr(
            usage,
            "output_tokens",
            0,
        )
        or 0
    )


    total_tokens = int(
        getattr(
            usage,
            "total_tokens",
            (
                input_tokens
                +
                output_tokens
            ),
        )
        or
        (
            input_tokens
            +
            output_tokens
        )
    )


    return {
        "tokens_entrada":
            input_tokens,

        "tokens_salida":
            output_tokens,

        "tokens_total":
            total_tokens,
    }
