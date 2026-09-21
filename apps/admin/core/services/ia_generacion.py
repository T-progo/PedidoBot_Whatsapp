"""
Servicio central de generación IA para NegocioListo.

TNL-IA-GENERACION-SERVICE-V1

Reglas:
- Toda generación valida primero la bolsa comercial.
- El modelo se obtiene de ConfiguracionIA.
- OpenAI se consume mediante Responses API.
- La respuesta entregada nunca excede el saldo comercial.
- Tokens de entrada/salida se registran para auditoría.
- Las palabras de salida descuentan la BolsaIA.
- Typebot NO debe llamar directamente a OpenAI.
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from core.models import ConfiguracionIA

from core.services.ia_bolsa import (
    BolsaIAAgotadaError,
    SaldoIAInsuficienteError,
    contar_palabras,
    limitar_texto_a_palabras,
    obtener_estado_ia,
    registrar_consumo_respuesta,
    validar_disponibilidad_ia,
)

from core.services.openai_provider import (
    OPENAI_MODEL_DEFAULT,
    crear_cliente,
    extraer_uso,
)


class GeneracionIAError(Exception):
    """Error base de generación IA."""


class EntradaIAInvalidaError(GeneracionIAError):
    """La entrada solicitada no es válida."""


class ProveedorIAError(GeneracionIAError):
    """El proveedor IA no pudo generar una respuesta válida."""


def _tokens_desde_uso(
    uso: dict[str, Any],
) -> tuple[int, int, int]:
    """
    Tolera nombres internos en español o nombres
    nativos de OpenAI.
    """

    entrada = int(
        uso.get(
            "tokens_entrada",
            uso.get(
                "input_tokens",
                0,
            ),
        )
        or 0
    )

    salida = int(
        uso.get(
            "tokens_salida",
            uso.get(
                "output_tokens",
                0,
            ),
        )
        or 0
    )

    total = int(
        uso.get(
            "tokens_total",
            uso.get(
                "total_tokens",
                entrada + salida,
            ),
        )
        or
        (
            entrada
            +
            salida
        )
    )

    return (
        max(0, entrada),
        max(0, salida),
        max(0, total),
    )


def _guardar_error_generico(
    *,
    empresa_id: int,
    mensaje: str,
) -> None:

    config = (
        ConfiguracionIA.objects
        .filter(
            empresa_id=empresa_id
        )
        .first()
    )

    if config is None:
        return

    config.ultimo_error = mensaje
    config.actualizado_en = timezone.now()

    config.save(
        update_fields=[
            "ultimo_error",
            "actualizado_en",
        ]
    )


def _limpiar_error(
    *,
    empresa_id: int,
) -> None:

    config = (
        ConfiguracionIA.objects
        .filter(
            empresa_id=empresa_id
        )
        .first()
    )

    if config is None:
        return

    if not config.ultimo_error:
        return

    config.ultimo_error = ""
    config.actualizado_en = timezone.now()

    config.save(
        update_fields=[
            "ultimo_error",
            "actualizado_en",
        ]
    )


# TNL-IA-HISTORY-INPUT-V1
def _normalizar_historial_entrada(
    historial,
) -> list[dict]:
    """
    Normaliza contexto conversacional exclusivamente
    como mensajes user/assistant.

    Nunca admite system/developer/tool.
    """

    if not isinstance(
        historial,
        (
            list,
            tuple,
        ),
    ):
        return []


    resultado = []


    for item in list(
        historial
    )[-12:]:

        if not isinstance(
            item,
            dict,
        ):
            continue


        role = str(
            item.get(
                "role"
            )
            or
            ""
        ).strip()


        if role not in {
            "user",
            "assistant",
        }:
            continue


        content = str(
            item.get(
                "content"
            )
            or
            ""
        ).strip()


        if not content:
            continue


        if len(content) > 4000:

            content = content[
                :4000
            ].rstrip()


        resultado.append(
            {
                "role":
                    role,

                "content":
                    content,
            }
        )


    if len(resultado) > 12:

        resultado = resultado[
            -12:
        ]


    return resultado


def generar_respuesta_ia(
    *,
    empresa_id: int,
    entrada: str,
    instrucciones: str = "",
    referencia_conversacion: str = "",
    origen: str = "",
    historial: list[dict] | None = None,
    max_palabras: int = 120,
) -> dict:
    """
    Genera y registra una respuesta comercial IA.

    El límite comercial es en PALABRAS.
    max_output_tokens es únicamente una protección
    técnica adicional frente al proveedor.
    """

    entrada = str(
        entrada
        or ""
    ).strip()

    if not entrada:

        raise EntradaIAInvalidaError(
            "La entrada IA está vacía."
        )


    try:

        max_palabras = int(
            max_palabras
        )

    except (
        TypeError,
        ValueError,
    ):

        raise EntradaIAInvalidaError(
            "max_palabras no es válido."
        )


    if max_palabras <= 0:

        raise EntradaIAInvalidaError(
            "max_palabras debe ser mayor que cero."
        )


    # Evita respuestas desproporcionadas desde
    # cualquier futuro consumidor del servicio.
    max_palabras = min(
        max_palabras,
        400,
    )


    estado_pre = validar_disponibilidad_ia(
        empresa_id
    )


    disponibles_pre = int(
        estado_pre[
            "palabras_disponibles"
        ]
    )


    if disponibles_pre <= 0:

        raise BolsaIAAgotadaError(
            "No existe saldo IA disponible."
        )


    limite_comercial = min(
        max_palabras,
        disponibles_pre,
    )


    modelo = (
        str(
            estado_pre.get(
                "modelo"
            )
            or ""
        ).strip()
        or
        OPENAI_MODEL_DEFAULT
    )


    # Con reasoning=none, este límite queda destinado
    # principalmente al texto visible.
    #
    # Se usa margen suficiente porque tokens != palabras.
    max_output_tokens = min(
        1600,
        max(
            64,
            limite_comercial * 4,
        ),
    )


    instrucciones_finales = (
        str(
            instrucciones
            or ""
        ).strip()
        or
        (
            "Responde en español de forma clara, "
            "útil y concisa. "
            "No excedas el límite solicitado."
        )
    )


    historial_normalizado = (
        _normalizar_historial_entrada(
            historial
        )
    )


    if historial_normalizado:

        input_final = [
            *historial_normalizado,
            {
                "role":
                    "user",

                "content":
                    entrada,
            },
        ]

    else:

        input_final = entrada


    try:

        cliente = crear_cliente()

        response = (
            cliente.responses.create(
                model=modelo,
                instructions=
                    instrucciones_finales,
                input=input_final,
                reasoning={
                    "effort": "none",
                },
                max_output_tokens=
                    max_output_tokens,
                store=False,
            )
        )

    except Exception as exc:

        _guardar_error_generico(
            empresa_id=empresa_id,
            mensaje=(
                "No fue posible obtener "
                "respuesta del proveedor OpenAI."
            ),
        )

        raise ProveedorIAError(
            "No fue posible generar "
            "la respuesta IA."
        ) from exc


    texto_original = str(
        getattr(
            response,
            "output_text",
            "",
        )
        or ""
    ).strip()


    if not texto_original:

        _guardar_error_generico(
            empresa_id=empresa_id,
            mensaje=(
                "OpenAI no devolvió "
                "texto utilizable."
            ),
        )

        raise ProveedorIAError(
            "El proveedor no devolvió "
            "texto utilizable."
        )


    # Nunca entregar más palabras que el saldo
    # observado antes de la llamada.
    texto_salida = limitar_texto_a_palabras(
        texto_original,
        limite_comercial,
    )


    palabras_salida = contar_palabras(
        texto_salida
    )


    if palabras_salida <= 0:

        raise ProveedorIAError(
            "La respuesta no contiene "
            "palabras contabilizables."
        )


    uso = extraer_uso(
        response
    )

    (
        tokens_entrada,
        tokens_salida,
        tokens_total,
    ) = _tokens_desde_uso(
        uso
    )


    # Autoridad transaccional final.
    #
    # Si otra petición consumió saldo entre el
    # pre-check y esta operación, reducimos el texto
    # al saldo actual SIN realizar otra llamada a OpenAI.
    try:

        consumo = registrar_consumo_respuesta(
            empresa_id=empresa_id,
            texto_salida=texto_salida,
            tokens_entrada=
                tokens_entrada,
            tokens_salida=
                tokens_salida,
            modelo=modelo,
            referencia_conversacion=
                referencia_conversacion,
            origen=origen,
        )

    except SaldoIAInsuficienteError:

        estado_actual = validar_disponibilidad_ia(
            empresa_id
        )

        disponibles_actuales = int(
            estado_actual[
                "palabras_disponibles"
            ]
        )

        if disponibles_actuales <= 0:

            raise BolsaIAAgotadaError(
                "La bolsa IA se agotó "
                "durante la generación."
            )


        texto_salida = limitar_texto_a_palabras(
            texto_salida,
            disponibles_actuales,
        )


        consumo = registrar_consumo_respuesta(
            empresa_id=empresa_id,
            texto_salida=texto_salida,
            tokens_entrada=
                tokens_entrada,
            tokens_salida=
                tokens_salida,
            modelo=modelo,
            referencia_conversacion=
                referencia_conversacion,
            origen=origen,
        )


    estado_post = obtener_estado_ia(
        empresa_id
    )


    _limpiar_error(
        empresa_id=empresa_id
    )


    return {
        "ok": True,
        "respuesta":
            texto_salida,

        "modelo":
            modelo,

        "palabras_salida":
            consumo.palabras_salida,

        "tokens_entrada":
            tokens_entrada,

        "tokens_salida":
            tokens_salida,

        "tokens_total":
            tokens_total,

        "consumo_id":
            consumo.id,

        "bolsa_id":
            consumo.bolsa_id,

        "palabras_disponibles":
            estado_post[
                "palabras_disponibles"
            ],

        "ia_habilitada":
            estado_post[
                "puede_usar_ia"
            ],
    }
