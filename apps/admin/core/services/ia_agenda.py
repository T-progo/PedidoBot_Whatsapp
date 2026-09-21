"""
TNL-IA-AGENDA-SERVICE-V1

Orquestación controlada entre IA y agenda.

Principio de seguridad:

- GPT interpreta intención, fecha y filtros horarios.
- GPT NO determina disponibilidad.
- GPT NO crea eventos.
- Google Calendar FreeBusy continúa siendo autoridad
  sobre ocupación.
- Las reglas comerciales de ConfiguracionAgenda /
  HorarioAtencion continúan siendo obligatorias.
"""

import re
import unicodedata

from datetime import (
    date,
    datetime,
    time,
)

from zoneinfo import (
    ZoneInfo,
    ZoneInfoNotFoundError,
)

from django.utils import timezone

from core.models import (
    ConfiguracionGoogleCalendar,
)

from core.services.google_calendar_citas import (
    GoogleCalendarCitasError,
    listar_slots_disponibles,
)

from core.services.ia_generacion import (
    generar_respuesta_ia,
)


class InterpretacionAgendaError(Exception):
    pass


def _normalizar_texto(
    texto,
):

    texto = str(
        texto or ""
    ).strip().lower()

    texto = unicodedata.normalize(
        "NFKD",
        texto,
    )

    return "".join(
        ch
        for ch in texto
        if not unicodedata.combining(
            ch
        )
    )


def parece_consulta_disponibilidad(
    mensaje,
):
    """
    Filtro determinista de intención de agenda.

    "Disponible/disponibilidad" por sí solo no implica
    agenda: también puede referirse a productos,
    inventario, servicios u otra información comercial.

    Las consultas con señales temporales o explícitas
    de cita/reserva sí continúan hacia el NLU de agenda.
    """

    texto = _normalizar_texto(
        mensaje
    )


    # TNL-IA-AGENDA-INTENT-GUARD-V2

    señales_fuertes = (
        "horario",
        "horarios",
        "hueco",
        "tienes lugar",
        "tienen lugar",
        "hay lugar",
        "espacio para cita",
        "espacio para una cita",
        "que horas tienes",
        "qué horas tienes",
    )


    if any(
        señal in texto
        for señal in señales_fuertes
    ):

        return True


    # Sin la palabra disponibilidad no necesitamos
    # aplicar el guard contextual de esta función.
    if "disponib" not in texto:

        # Estas señales explícitas siguen siendo agenda
        # si el orquestador de reserva previo no las
        # hubiera manejado.
        señales_agenda_explicita = (
            "cita",
            "citas",
            "agend",
            "reserv",
            "turno",
        )

        return any(
            señal in texto
            for señal in señales_agenda_explicita
        )


    # "Disponibilidad" requiere contexto adicional.
    contexto_agenda = (
        "cita",
        "citas",
        "agend",
        "reserv",
        "turno",
        "fecha",
        "hora",
        "horas",
        "hoy",
        "mañana",
        "manana",
        "lunes",
        "martes",
        "miércoles",
        "miercoles",
        "jueves",
        "viernes",
        "sábado",
        "sabado",
        "domingo",
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    )


    return any(
        señal in texto
        for señal in contexto_agenda
    )


def _parse_hora(
    valor,
):

    valor = str(
        valor or ""
    ).strip()


    if not valor:
        return None


    try:

        return datetime.strptime(
            valor,
            "%H:%M",
        ).time()

    except ValueError as exc:

        raise InterpretacionAgendaError(
            "La IA devolvió una hora inválida."
        ) from exc


def _extraer_protocolo(
    texto,
):

    texto = str(
        texto or ""
    ).strip()


    # Permite tolerar fences si el proveedor
    # llegara a envolver la línea.
    texto = texto.replace(
        "```text",
        "",
    ).replace(
        "```",
        "",
    ).strip()


    if texto == "FALTA_FECHA":

        return {
            "tipo":
                "FALTA_FECHA",
        }


    if texto == "OTRO":

        return {
            "tipo":
                "OTRO",
        }


    patron = re.compile(
        r"DISPONIBILIDAD\|"
        r"(\d{4}-\d{2}-\d{2})\|"
        r"([0-2]\d:[0-5]\d)?\|"
        r"([0-2]\d:[0-5]\d)?"
    )


    match = patron.search(
        texto
    )


    if match is None:

        return {
            "tipo":
                "NO_INTERPRETADO",
        }


    fecha_texto = match.group(
        1
    )

    try:

        fecha = date.fromisoformat(
            fecha_texto
        )

    except ValueError:

        return {
            "tipo":
                "NO_INTERPRETADO",
        }


    try:

        hora_desde = _parse_hora(
            match.group(
                2
            )
        )

        hora_hasta = _parse_hora(
            match.group(
                3
            )
        )

    except InterpretacionAgendaError:

        return {
            "tipo":
                "NO_INTERPRETADO",
        }


    if (
        hora_desde is not None
        and
        hora_hasta is not None
        and
        hora_hasta
        <=
        hora_desde
    ):

        return {
            "tipo":
                "NO_INTERPRETADO",
        }


    return {
        "tipo":
            "DISPONIBILIDAD",

        "fecha":
            fecha,

        "hora_desde":
            hora_desde,

        "hora_hasta":
            hora_hasta,
    }


def responder_disponibilidad_agenda_ia(
    *,
    empresa,
    mensaje,
    referencia_conversacion="",
):
    """
    Si el mensaje no parece una consulta de disponibilidad,
    retorna manejado=False y NO consume IA.

    Si parece una consulta:
      1. GPT interpreta los parámetros.
      2. Django valida el protocolo.
      3. Google / reglas comerciales calculan slots.
      4. La respuesta final se construye de forma
         determinista con los slots reales.
    """

    mensaje = str(
        mensaje or ""
    ).strip()


    if not parece_consulta_disponibilidad(
        mensaje
    ):

        return {
            "manejado":
                False,
        }


    try:

        config_google = (
            ConfiguracionGoogleCalendar.objects
            .get(
                empresa=empresa
            )
        )

    except ConfiguracionGoogleCalendar.DoesNotExist:

        return {
            "manejado":
                True,

            "accion":
                "agenda_no_configurada",

            "respuesta":
                (
                    "La agenda no está disponible "
                    "en este momento."
                ),

            "modelo":
                "",

            "palabras_salida":
                0,

            "palabras_disponibles":
                None,

            "fecha":
                "",

            "total_disponibles":
                0,

            "horarios":
                "",
        }


    try:

        zona = ZoneInfo(
            config_google.zona_horaria
        )

    except ZoneInfoNotFoundError as exc:

        raise GoogleCalendarCitasError(
            "La zona horaria de agenda no es válida."
        ) from exc


    ahora_local = (
        timezone.now()
        .astimezone(
            zona
        )
    )


    instrucciones = (
        "Eres exclusivamente un analizador de intención "
        "de agenda. NO respondas al usuario. "
        "NO inventes disponibilidad. "
        "Tu única tarea es convertir una solicitud de "
        "disponibilidad de citas a un protocolo exacto. "
        f"Fecha y hora local actual: "
        f"{ahora_local.isoformat()}. "
        f"Zona horaria: {config_google.zona_horaria}. "
        "Si el usuario pregunta por disponibilidad y existe "
        "una fecha resoluble, responde UNA sola línea y nada más: "
        "DISPONIBILIDAD|AAAA-MM-DD|HH:MM|HH:MM "
        "El tercer campo es hora_desde y el cuarto hora_hasta; "
        "déjalos vacíos cuando no existan. "
        "Resuelve hoy, mañana y días de la semana respecto de "
        "la fecha local indicada. "
        "Si dice 'después de las 4' sin indicar mañana/tarde "
        "y el contexto es una cita comercial, interpreta 16:00. "
        "Si pregunta disponibilidad pero falta la fecha, "
        "responde exactamente FALTA_FECHA. "
        "Si está preguntando solamente el horario de apertura "
        "del negocio o el mensaje no corresponde a disponibilidad "
        "de una cita, responde exactamente OTRO. "
        "No uses Markdown. No expliques el resultado."
    )


    interpretacion_ia = generar_respuesta_ia(
        empresa_id=
            empresa.pk,

        entrada=
            mensaje,

        instrucciones=
            instrucciones,

        referencia_conversacion=
            referencia_conversacion,

        origen=
            "typebot_agenda_nlu",

        max_palabras=
            12,
    )


    protocolo = _extraer_protocolo(
        interpretacion_ia[
            "respuesta"
        ]
    )


    tipo = protocolo[
        "tipo"
    ]


    # -------------------------------------------------------------
    # No permitimos una segunda llamada a IA.
    # Si la interpretación no es operable se responde
    # determinísticamente.
    # -------------------------------------------------------------

    if tipo == "FALTA_FECHA":

        return {
            "manejado":
                True,

            "accion":
                "agenda_falta_fecha",

            "respuesta":
                (
                    "Claro. ¿Para qué fecha quieres "
                    "consultar disponibilidad?"
                ),

            "modelo":
                interpretacion_ia[
                    "modelo"
                ],

            "palabras_salida":
                interpretacion_ia[
                    "palabras_salida"
                ],

            "palabras_disponibles":
                interpretacion_ia[
                    "palabras_disponibles"
                ],

            "fecha":
                "",

            "total_disponibles":
                0,

            "horarios":
                "",
        }


    # TNL-IA-AGENDA-OTRO-FALLTHROUGH-V1
    #
    # El NLU técnico ya determinó que el mensaje no
    # corresponde a disponibilidad de una cita.
    # No debemos convertir OTRO en una aclaración de
    # agenda: dejamos continuar hacia la IA general,
    # donde además participa la memoria conversacional.
    if tipo in {
        "OTRO",
        "NO_INTERPRETADO",
    }:

        return {
            "manejado":
                False,
        }


    fecha = protocolo[
        "fecha"
    ]

    hora_desde = protocolo[
        "hora_desde"
    ]

    hora_hasta = protocolo[
        "hora_hasta"
    ]


    resultado = listar_slots_disponibles(
        empresa=empresa,
        fecha=fecha,
        hora_desde=hora_desde,
        hora_hasta=hora_hasta,
    )


    slots = (
        resultado.get(
            "slots"
        )
        or []
    )


    horas = [
        str(
            slot.get(
                "hora"
            )
            or
            ""
        ).strip()
        for slot in slots
        if str(
            slot.get(
                "hora"
            )
            or
            ""
        ).strip()
    ]


    horarios_texto = ", ".join(
        horas
    )


    fecha_usuario = fecha.strftime(
        "%d/%m/%Y"
    )


    if resultado[
        "dia_cerrado"
    ]:

        respuesta = (
            f"El {fecha_usuario} no ofrecemos citas. "
            "Si quieres, dime otra fecha."
        )


    elif not horas:

        respuesta = (
            f"No tengo horarios disponibles para el "
            f"{fecha_usuario} con esos criterios. "
            "Puedes indicarme otra fecha u horario."
        )


    else:

        # El máximo actual es pequeño y permite mostrar
        # los slots completos sin depender de GPT.
        respuesta = (
            f"Para el {fecha_usuario} tengo disponibles: "
            f"{horarios_texto}. "
            "¿Qué horario prefieres?"
        )


    return {
        "manejado":
            True,

        "accion":
            "agenda_disponibilidad",

        "respuesta":
            respuesta,

        "modelo":
            interpretacion_ia[
                "modelo"
            ],

        "palabras_salida":
            interpretacion_ia[
                "palabras_salida"
            ],

        "palabras_disponibles":
            interpretacion_ia[
                "palabras_disponibles"
            ],

        "fecha":
            resultado[
                "fecha"
            ],

        "total_disponibles":
            len(
                horas
            ),

        "horarios":
            horarios_texto,

        "dia_cerrado":
            bool(
                resultado[
                    "dia_cerrado"
                ]
            ),

        "bloques_ocupados_google":
            resultado[
                "bloques_ocupados_google"
            ],
    }
