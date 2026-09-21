"""
Notificaciones operativas de pedidos por WhatsApp.

No controla estados del pedido.
No modifica inventario.
No modifica Pedido.
"""

import re

from core.integrations.evolution_client import (
    EvolutionClient,
    EvolutionClientError,
)


# ============================================================
# TNL-PEDIDO-WHATSAPP-STATUS-V1
# ============================================================


_INSTANCE_RE = re.compile(
    r"^tnl-e[1-9][0-9]*-i[1-9][0-9]*$"
)


_MENSAJES_ESTADO = {

    "preparando":
        (
            "🟡 ¡Tu pedido {numero} está siendo preparado! "
            "Te avisaremos cuando avance al siguiente paso."
        ),

    "enviado":
        (
            "🚚 ¡Tu pedido {numero} ya fue despachado "
            "y está avanzando hacia la entrega!"
        ),

    "entregado":
        (
            "✅ Tu pedido {numero} ha sido marcado como entregado. "
            "¡Gracias por tu compra!"
        ),
}


def normalizar_numero_whatsapp(
    valor,
    *,
    codigo_pais_default="52",
) -> str:
    """
    Normaliza el teléfono del pedido para Evolution.

    Para México:
    - 10 dígitos -> antepone 52.
    - 52 + 10 dígitos -> conserva.
    - 521 + 10 dígitos -> elimina el antiguo 1 móvil.
    - otros números internacionales de 11-15 dígitos
      se conservan.
    """

    digits = "".join(
        character
        for character in str(
            valor
            or ""
        )
        if character.isdigit()
    )


    if not digits:

        return ""


    if (
        len(digits) == 13
        and
        digits.startswith("521")
    ):

        digits = (
            "52"
            +
            digits[3:]
        )


    if len(digits) == 10:

        digits = (
            str(
                codigo_pais_default
                or "52"
            )
            +
            digits
        )


    if not (
        11
        <=
        len(digits)
        <=
        15
    ):

        return ""


    return digits


def construir_mensaje_estado_pedido(
    *,
    numero,
    estado,
    tipo_orden="",
    empresa_id=None,
    bot_id=None,
) -> str:

    estado = str(
        estado
        or ""
    ).strip().lower()

    tipo_orden = str(
        tipo_orden
        or ""
    ).strip().lower()

    numero = str(
        numero
        or ""
    ).strip()

    if not numero:

        return ""

    # ============================================================
    # TNL-PEDIDO-WHATSAPP-EVENTO-R4-V1
    # ============================================================

    # TNL-RESTAURANTE-MP-PAGADO-WHATSAPP-V1
    #
    # Pago confirmado automáticamente por el webhook MP.
    # Sólo aplica a tipos de orden Restaurante.
    if estado == "pagado":

        if tipo_orden not in {
            "comedor",
            "para_llevar",
            "domicilio",
        }:

            return ""

        return (
            f"✅ Pago confirmado para tu pedido {numero}. "
            "Tu pago fue recibido correctamente."
        )

    # TNL-RESTAURANTE-CANCELACION-PANEL-R6-V1
    if estado == "cancelado":

        if tipo_orden not in {
            "comedor",
            "para_llevar",
            "domicilio",
        }:

            return ""

        return (
            f"❌ Tu pedido {numero} ha sido cancelado."
        )

    if estado == "listo":

        if tipo_orden == "para_llevar":

            return (
                f"🍔 ¡Tu pedido {numero} está listo! "
                "Ya puedes pasar a recogerlo."
            )

        if tipo_orden == "domicilio":

            return (
                f"🍔 ¡Tu pedido {numero} está listo! "
                "En breve saldrá rumbo a tu domicilio."
            )

        if tipo_orden == "comedor":

            return (
                f"🍔 ¡Tu pedido {numero} está listo!"
            )

        return ""

    if estado == "en_camino":

        if tipo_orden != "domicilio":

            return ""

        return (
            f"🛵 ¡Tu pedido {numero} va en camino! "
            "Nuestro repartidor ya salió con tu orden."
        )

    template = (
        _MENSAJES_ESTADO.get(
            estado
        )
    )

    if not template:

        return ""

    return template.format(
        numero=numero
    )



def _estado_instancia(
    item,
) -> str:

    if not isinstance(
        item,
        dict,
    ):

        return ""


    return str(
        item.get("state")
        or
        item.get("connectionStatus")
        or
        item.get("status")
        or
        ""
    ).strip().lower()


def _extraer_message_id_evolution(
    respuesta,
) -> str:

    if not isinstance(
        respuesta,
        dict,
    ):
        return ""

    candidatos = [
        respuesta.get("messageId"),
        respuesta.get("message_id"),
        respuesta.get("id"),
    ]

    key = respuesta.get("key")

    if isinstance(
        key,
        dict,
    ):
        candidatos.append(
            key.get("id")
        )

    message = respuesta.get(
        "message"
    )

    if isinstance(
        message,
        dict,
    ):

        candidatos.extend(
            [
                message.get(
                    "messageId"
                ),
                message.get(
                    "id"
                ),
            ]
        )

        message_key = (
            message.get(
                "key"
            )
        )

        if isinstance(
            message_key,
            dict,
        ):
            candidatos.append(
                message_key.get(
                    "id"
                )
            )

    for candidato in candidatos:

        value = str(
            candidato
            or ""
        ).strip()

        if value:
            return value

    return ""


def _enviar_estado_pedido_whatsapp(
    *,
    pedido,
) -> dict:
    """
    Notificador legacy preservado.

    R4 sólo amplía:
    - tipo_orden al constructor;
    - message_id en la respuesta.
    """

    if not getattr(
        pedido,
        "canal_id",
        None,
    ):

        return {
            "enviado": False,
            "aplicable": False,
            "motivo":
                (
                    "El pedido no está asociado "
                    "a un canal WhatsApp."
                ),
            "message_id": "",
        }

    canal = getattr(
        pedido,
        "canal",
        None,
    )

    if canal is None:

        return {
            "enviado": False,
            "aplicable": False,
            "motivo":
                "No fue posible resolver el canal del pedido.",
            "message_id": "",
        }

    if str(
        getattr(
            canal,
            "tipo",
            "",
        )
        or ""
    ).strip().lower() != "whatsapp":

        return {
            "enviado": False,
            "aplicable": False,
            "motivo":
                "El pedido no proviene de WhatsApp.",
            "message_id": "",
        }

    bot = getattr(
        canal,
        "bot",
        None,
    )

    if (
        bot is None
        or
        getattr(
            bot,
            "empresa_id",
            None,
        )
        !=
        getattr(
            pedido,
            "empresa_id",
            None,
        )
    ):

        return {
            "enviado": False,
            "aplicable": False,
            "motivo":
                "El canal no corresponde a la empresa del pedido.",
            "message_id": "",
        }

    if not bool(
        getattr(
            canal,
            "activo",
            False,
        )
    ):

        return {
            "enviado": False,
            "aplicable": True,
            "motivo":
                "El canal WhatsApp está inactivo.",
            "message_id": "",
        }

    instance_name = str(
        getattr(
            canal,
            "identificador",
            "",
        )
        or ""
    ).strip()

    if not _INSTANCE_RE.fullmatch(
        instance_name
    ):

        return {
            "enviado": False,
            "aplicable": True,
            "motivo":
                "El canal WhatsApp no tiene una instancia válida.",
            "message_id": "",
        }

    number = (
        normalizar_numero_whatsapp(
            getattr(
                pedido,
                "cliente_telefono",
                "",
            )
        )
    )

    if not number:

        return {
            "enviado": False,
            "aplicable": True,
            "motivo":
                "El teléfono del cliente no es válido para WhatsApp.",
            "message_id": "",
        }

    message = (
        construir_mensaje_estado_pedido(
            numero=getattr(
                pedido,
                "numero",
                "",
            ),

            estado=getattr(
                pedido,
                "estado",
                "",
            ),

            tipo_orden=getattr(
                pedido,
                "tipo_orden",
                "",
            ),

            empresa_id=getattr(
                pedido,
                "empresa_id",
                None,
            ),

            bot_id=getattr(
                bot,
                "id",
                None,
            ),
        )
    )

    if not message:

        return {
            "enviado": False,
            "aplicable": False,
            "motivo":
                "El estado no requiere notificación WhatsApp.",
            "message_id": "",
        }

    client = EvolutionClient()

    try:

        instance = (
            client.find_instance(
                instance_name
            )
        )

        if (
            _estado_instancia(
                instance
            )
            !=
            "open"
        ):

            return {
                "enviado": False,
                "aplicable": True,
                "motivo":
                    "La sesión WhatsApp no está abierta.",
                "message_id": "",
            }

        respuesta = (
            client.send_text(
                instance_name=
                    instance_name,

                number=
                    number,

                text=
                    message,

                timeout=
                    20,
            )
        )

    except EvolutionClientError:

        return {
            "enviado": False,
            "aplicable": True,
            "motivo":
                (
                    "Evolution no pudo enviar "
                    "la notificación WhatsApp."
                ),
            "message_id": "",
        }

    return {
        "enviado": True,
        "aplicable": True,
        "motivo": "",
        "message_id":
            _extraer_message_id_evolution(
                respuesta
            ),
    }


def notificar_estado_pedido_whatsapp(
    *,
    pedido,
) -> dict:
    """
    Wrapper histórico/legacy.

    TNL-PEDIDO-WHATSAPP-MOTOR-COMPARTIDO-R4-V1

    Se mantiene como superficie pública legacy.
    Restaurante por evento NO depende de este wrapper.
    """

    return _enviar_estado_pedido_whatsapp(
        pedido=pedido
    )



_ESTADOS_EVENTO_RESTAURANTE_WA = {
    "pagado",
    "preparando",
    "listo",
    "en_camino",
    "entregado",
    "cancelado",
}


def notificar_evento_pedido_whatsapp(
    *,
    evento_id,
) -> dict:
    """
    Envío Restaurante idempotente por PedidoEstadoEvento.

    Claim:
      notificacion_whatsapp_intentada_en

    Semántica:
      at-most-once automático.

    IMPORTANTE:
      se bloquea exclusivamente PedidoEstadoEvento.
      Pedido.canal es nullable y NO forma parte del FOR UPDATE.
    """

    from types import (
        SimpleNamespace,
    )

    from django.db import (
        transaction,
    )

    from django.utils import (
        timezone,
    )

    from core.models import (
        PedidoEstadoEvento,
    )

    try:

        evento_id = int(
            evento_id
        )

    except (
        TypeError,
        ValueError,
    ):

        evento_id = 0

    if evento_id <= 0:

        return {
            "enviado": False,
            "aplicable": False,
            "motivo":
                "El evento de pedido no es válido.",
            "message_id": "",
            "idempotente": True,
        }

    # ============================================================
    # CLAIM IDEMPOTENTE
    #
    # PostgreSQL:
    # select_for_update(of=("self",))
    #
    # Evita bloquear los LEFT OUTER JOIN derivados de
    # pedido__canal, ya que Pedido.canal puede ser NULL.
    # ============================================================

    with transaction.atomic():

        evento = (
            PedidoEstadoEvento.objects
            .select_for_update(
                of=("self",)
            )
            .select_related(
                "pedido",
                "pedido__canal",
                "pedido__canal__bot",
            )
            .filter(
                pk=evento_id
            )
            .first()
        )

        if evento is None:

            return {
                "enviado": False,
                "aplicable": False,
                "motivo":
                    "El evento de pedido no existe.",
                "message_id": "",
                "idempotente": True,
            }

        pedido = evento.pedido

        tipo_orden = str(
            pedido.tipo_orden
            or ""
        ).strip().lower()

        estado_nuevo = str(
            evento.estado_nuevo
            or ""
        ).strip().lower()

        if tipo_orden not in {
            "comedor",
            "para_llevar",
            "domicilio",
        }:

            return {
                "enviado": False,
                "aplicable": False,
                "motivo":
                    (
                        "El evento no pertenece "
                        "a un pedido Restaurante."
                    ),
                "message_id": "",
                "idempotente": True,
            }

        # ============================================================
        # TNL-RESTAURANTE-CANCELACION-PANEL-REUSABLE-V1
        #
        # Cancelación aplica al contrato Restaurante validado
        # arriba mediante tipo_orden.
        # ============================================================

        # TNL-RESTAURANTE-MP-PAGADO-WHATSAPP-V1
        #
        # "pagado" utiliza el mismo gate Restaurante
        # validado arriba mediante tipo_orden.

        if (
            estado_nuevo
            not in
            _ESTADOS_EVENTO_RESTAURANTE_WA
        ):

            return {
                "enviado": False,
                "aplicable": False,
                "motivo":
                    (
                        "El estado no requiere "
                        "notificación Restaurante."
                    ),
                "message_id": "",
                "idempotente": True,
            }

        if (
            estado_nuevo == "en_camino"
            and
            tipo_orden != "domicilio"
        ):

            return {
                "enviado": False,
                "aplicable": False,
                "motivo":
                    (
                        "En camino sólo aplica "
                        "a pedidos a domicilio."
                    ),
                "message_id": "",
                "idempotente": True,
            }

        if (
            evento
            .notificacion_whatsapp_enviada
        ):

            return {
                "enviado": True,
                "aplicable": True,
                "motivo": "",
                "message_id":
                    evento.message_id,
                "idempotente": True,
            }

        if (
            evento
            .notificacion_whatsapp_intentada_en
            is not None
        ):

            return {
                "enviado": False,
                "aplicable": True,
                "motivo":
                    (
                        evento.notificacion_error
                        or
                        (
                            "La notificación "
                            "ya fue intentada."
                        )
                    ),
                "message_id":
                    evento.message_id,
                "idempotente": True,
            }

        evento.notificacion_whatsapp_intentada_en = (
            timezone.now()
        )

        evento.notificacion_error = ""

        evento.save(
            update_fields=[
                "notificacion_whatsapp_intentada_en",
                "notificacion_error",
            ]
        )

        # Datos necesarios para enviar fuera de la transacción.
        pedido_notificable = (
            SimpleNamespace(
                canal_id=
                    pedido.canal_id,

                canal=
                    pedido.canal,

                empresa_id=
                    pedido.empresa_id,

                cliente_telefono=
                    pedido.cliente_telefono,

                numero=
                    pedido.numero,

                estado=
                    estado_nuevo,

                tipo_orden=
                    tipo_orden,
            )
        )

    # Side effect externo fuera del lock/transacción.
    resultado = (
        _enviar_estado_pedido_whatsapp(
            pedido=
                pedido_notificable
        )
    )

    # Persistencia del resultado.
    with transaction.atomic():

        evento = (
            PedidoEstadoEvento.objects
            .select_for_update(
                of=("self",)
            )
            .get(
                pk=evento_id
            )
        )

        if resultado.get(
            "enviado"
        ):

            max_length = (
                PedidoEstadoEvento
                ._meta
                .get_field(
                    "message_id"
                )
                .max_length
                or
                255
            )

            evento.notificacion_whatsapp_enviada = (
                True
            )

            evento.message_id = str(
                resultado.get(
                    "message_id"
                )
                or ""
            )[:max_length]

            evento.notificacion_error = ""

        else:

            evento.notificacion_whatsapp_enviada = (
                False
            )

            evento.message_id = ""

            evento.notificacion_error = str(
                resultado.get(
                    "motivo"
                )
                or
                (
                    "No fue posible enviar "
                    "la notificación WhatsApp."
                )
            )[:2000]

        evento.save(
            update_fields=[
                "notificacion_whatsapp_enviada",
                "message_id",
                "notificacion_error",
            ]
        )

    return {
        **resultado,

        "evento_id":
            evento_id,

        "idempotente":
            False,
    }


