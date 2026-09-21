"""
TNL-IA-AGENDA-RESERVA-SERVICE-V1

Reserva de citas desde IA con confirmación autocontenida.

Seguridad:

1. GPT únicamente interpreta la solicitud inicial.
2. La disponibilidad proviene de Django + Google.
3. La solicitud inicial JAMÁS crea una Cita.
4. Sólo una frase de confirmación completa puede crearla.
5. La confirmación NO usa GPT.
6. crear_cita() vuelve a validar disponibilidad
   inmediatamente antes de escribir Google.
"""

import re
import unicodedata

from datetime import (
    date,
    datetime,
    timedelta,
    timezone as datetime_timezone,
)

from zoneinfo import (
    ZoneInfo,
    ZoneInfoNotFoundError,
)

from django.utils import timezone

from core.models import (
    Cita,
    ConfiguracionAgenda,
    ConfiguracionGoogleCalendar,
)

from core.services.google_calendar_citas import (
    GoogleCalendarCitasError,
    GoogleCalendarHorarioOcupadoError,
    crear_cita,
    listar_slots_disponibles,
)

from core.services.ia_generacion import (
    generar_respuesta_ia,
)


def _normalizar(
    value,
):

    value = str(
        value or ""
    ).strip().lower()

    value = unicodedata.normalize(
        "NFKD",
        value,
    )

    return "".join(
        char
        for char in value
        if not unicodedata.combining(
            char
        )
    )


def parece_solicitud_reserva(
    mensaje,
):

    texto = _normalizar(
        mensaje
    )

    señales = (
        "agendame",
        "agendarme",
        "quiero agendar",
        "quiero reservar",
        "reservame",
        "reservar una cita",
        "agenda una cita",
        "agendar una cita",
        "apartame una cita",
        "aparta una cita",
    )

    return any(
        señal in texto
        for señal in señales
    )


def _parse_confirmacion(
    mensaje,
):
    """
    ÚNICA sintaxis que puede autorizar creación:

    Confirmar cita AAAA-MM-DD HH:MM a nombre de NOMBRE

    La coincidencia es total, no parcial.
    """

    texto = str(
        mensaje or ""
    ).strip()


    patron = re.compile(
        r"^confirmar\s+cita\s+"
        r"(\d{4}-\d{2}-\d{2})\s+"
        r"([0-2]\d:[0-5]\d)\s+"
        r"a\s+nombre\s+de\s+"
        r"(.{2,200})$",
        re.IGNORECASE,
    )


    match = patron.fullmatch(
        texto
    )


    if match is None:
        return None


    fecha_texto = match.group(
        1
    )

    hora_texto = match.group(
        2
    )

    nombre = match.group(
        3
    ).strip()


    if _normalizar(
        nombre
    ) in {
        "tu nombre",
        "nombre",
    }:
        return None


    try:

        fecha = date.fromisoformat(
            fecha_texto
        )

        hora = datetime.strptime(
            hora_texto,
            "%H:%M",
        ).time()

    except ValueError:
        return None


    return {
        "fecha":
            fecha,

        "hora":
            hora,

        "nombre":
            nombre,
    }


def _localizar_seguro(
    *,
    fecha,
    hora,
    zona,
):

    naive = datetime.combine(
        fecha,
        hora,
    )

    candidatos = []


    for fold in (
        0,
        1,
    ):

        aware = naive.replace(
            tzinfo=zona,
            fold=fold,
        )

        roundtrip = (
            aware
            .astimezone(
                datetime_timezone.utc
            )
            .astimezone(
                zona
            )
        )


        if (
            roundtrip.replace(
                tzinfo=None
            )
            ==
            naive
        ):

            candidatos.append(
                aware
            )


    if not candidatos:

        raise GoogleCalendarCitasError(
            "El horario solicitado no existe por un cambio de zona horaria."
        )


    offsets = {
        candidato.utcoffset()
        for candidato in candidatos
    }


    if len(offsets) > 1:

        raise GoogleCalendarCitasError(
            "El horario solicitado es ambiguo por un cambio de zona horaria."
        )


    return candidatos[0]


def _parse_nlu_reserva(
    texto,
):

    texto = str(
        texto or ""
    ).strip()

    texto = (
        texto
        .replace(
            "```text",
            "",
        )
        .replace(
            "```",
            "",
        )
        .strip()
    )


    if texto in {
        "FALTA_FECHA",
        "FALTA_HORA",
        "OTRO",
    }:

        return {
            "tipo":
                texto,
        }


    match = re.fullmatch(
        r"RESERVA\|"
        r"(\d{4}-\d{2}-\d{2})\|"
        r"([0-2]\d:[0-5]\d)",
        texto,
    )


    if match is None:

        return {
            "tipo":
                "NO_INTERPRETADO",
        }


    try:

        fecha = date.fromisoformat(
            match.group(
                1
            )
        )

        hora = datetime.strptime(
            match.group(
                2
            ),
            "%H:%M",
        ).time()

    except ValueError:

        return {
            "tipo":
                "NO_INTERPRETADO",
        }


    return {
        "tipo":
            "RESERVA",

        "fecha":
            fecha,

        "hora":
            hora,
    }


def responder_reserva_agenda_ia(
    *,
    empresa,
    bot,
    mensaje,
    referencia_conversacion="",
):
    """
    Retorna manejado=False cuando el mensaje
    no corresponde a reserva.

    Una confirmación completa se procesa ANTES
    de cualquier llamada a GPT.
    """

    mensaje = str(
        mensaje or ""
    ).strip()


    # =================================================================
    # 1. CONFIRMACION AUTOCONTENIDA.
    #    NO GPT.
    # =================================================================

    confirmacion = _parse_confirmacion(
        mensaje
    )


    if confirmacion is not None:

        try:

            agenda = (
                ConfiguracionAgenda.objects
                .get(
                    empresa=empresa
                )
            )

            config_google = (
                ConfiguracionGoogleCalendar.objects
                .get(
                    empresa=empresa
                )
            )

        except (
            ConfiguracionAgenda.DoesNotExist,
            ConfiguracionGoogleCalendar.DoesNotExist,
        ):

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

                "cita_id":
                    None,

                "estado":
                    "",
            }


        try:

            zona = ZoneInfo(
                config_google.zona_horaria
            )

        except ZoneInfoNotFoundError:

            return {
                "manejado":
                    True,

                "accion":
                    "agenda_error",

                "respuesta":
                    (
                        "La agenda no está disponible "
                        "temporalmente."
                    ),

                "modelo":
                    "",

                "palabras_salida":
                    0,

                "palabras_disponibles":
                    None,

                "fecha":
                    confirmacion[
                        "fecha"
                    ].isoformat(),

                "total_disponibles":
                    0,

                "horarios":
                    "",

                "cita_id":
                    None,

                "estado":
                    "",
            }


        try:

            inicio = _localizar_seguro(
                fecha=
                    confirmacion[
                        "fecha"
                    ],

                hora=
                    confirmacion[
                        "hora"
                    ],

                zona=
                    zona,
            )


            fin = (
                inicio
                +
                timedelta(
                    minutes=
                        int(
                            agenda
                            .duracion_predeterminada_minutos
                        )
                )
            )


            cita = crear_cita(
                empresa=empresa,
                bot=bot,
                inicio=inicio,
                fin=fin,
                titulo=
                    (
                        "Cita - "
                        +
                        confirmacion[
                            "nombre"
                        ]
                    ),
                nombre_cliente=
                    confirmacion[
                        "nombre"
                    ],
                servicio=
                    "Cita",
                descripcion=
                    (
                        "Cita solicitada y confirmada "
                        "desde el Asistente IA "
                        "de NegocioListo."
                    ),
                referencia_conversacion=
                    str(
                        referencia_conversacion
                        or
                        ""
                    ).strip(),
                origen=
                    Cita.ORIGEN_CHATBOT,
            )


        except GoogleCalendarHorarioOcupadoError:

            return {
                "manejado":
                    True,

                "accion":
                    "agenda_horario_ya_no_disponible",

                "respuesta":
                    (
                        "Ese horario ya no está disponible. "
                        "Consúltame nuevamente los horarios "
                        "antes de confirmar otra cita."
                    ),

                "modelo":
                    "",

                "palabras_salida":
                    0,

                "palabras_disponibles":
                    None,

                "fecha":
                    confirmacion[
                        "fecha"
                    ].isoformat(),

                "total_disponibles":
                    0,

                "horarios":
                    "",

                "cita_id":
                    None,

                "estado":
                    "",
            }


        except GoogleCalendarCitasError:

            return {
                "manejado":
                    True,

                "accion":
                    "agenda_error",

                "respuesta":
                    (
                        "No fue posible crear la cita "
                        "en este momento. Inténtalo nuevamente."
                    ),

                "modelo":
                    "",

                "palabras_salida":
                    0,

                "palabras_disponibles":
                    None,

                "fecha":
                    confirmacion[
                        "fecha"
                    ].isoformat(),

                "total_disponibles":
                    0,

                "horarios":
                    "",

                "cita_id":
                    None,

                "estado":
                    "",
            }


        fecha_usuario = (
            confirmacion[
                "fecha"
            ].strftime(
                "%d/%m/%Y"
            )
        )

        hora_usuario = (
            confirmacion[
                "hora"
            ].strftime(
                "%H:%M"
            )
        )


        return {
            "manejado":
                True,

            "accion":
                "agenda_cita_creada",

            "respuesta":
                (
                    f"Listo, {confirmacion['nombre']}. "
                    f"Tu cita quedó confirmada para el "
                    f"{fecha_usuario} a las "
                    f"{hora_usuario}."
                ),

            "modelo":
                "",

            "palabras_salida":
                0,

            "palabras_disponibles":
                None,

            "fecha":
                confirmacion[
                    "fecha"
                ].isoformat(),

            "total_disponibles":
                0,

            "horarios":
                hora_usuario,

            "cita_id":
                cita.pk,

            "estado":
                cita.estado,
        }


    # =================================================================
    # 2. MENSAJE QUE NO ES RESERVA.
    # =================================================================

    if not parece_solicitud_reserva(
        mensaje
    ):

        return {
            "manejado":
                False,
        }


    # =================================================================
    # 3. GPT INTERPRETA LA SOLICITUD.
    #    NO DECIDE DISPONIBILIDAD.
    # =================================================================

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

            "cita_id":
                None,

            "estado":
                "",
        }


    try:

        zona = ZoneInfo(
            config_google.zona_horaria
        )

    except ZoneInfoNotFoundError as exc:

        raise GoogleCalendarCitasError(
            "La zona horaria configurada no es válida."
        ) from exc


    ahora_local = (
        timezone.now()
        .astimezone(
            zona
        )
    )


    instrucciones = (
        "Eres exclusivamente un analizador de una "
        "solicitud para RESERVAR una cita. "
        "NO respondas al usuario. "
        "NO inventes disponibilidad. "
        f"Fecha y hora local actual: "
        f"{ahora_local.isoformat()}. "
        f"Zona horaria: {config_google.zona_horaria}. "
        "Si existe una fecha y una hora concretas "
        "o resolubles, responde una sola línea: "
        "RESERVA|AAAA-MM-DD|HH:MM "
        "Resuelve hoy, mañana y nombres de días "
        "respecto de la fecha local indicada. "
        "Cuando el contexto sea una cita comercial, "
        "'a las 4' o '4:30' sin indicar mañana/tarde "
        "debe interpretarse como 16:00 o 16:30. "
        "Si falta la fecha responde exactamente "
        "FALTA_FECHA. "
        "Si falta la hora responde exactamente "
        "FALTA_HORA. "
        "Si no es una solicitud de reserva responde "
        "exactamente OTRO. "
        "No uses Markdown. No expliques nada."
    )


    interpretacion = generar_respuesta_ia(
        empresa_id=
            empresa.pk,

        entrada=
            mensaje,

        instrucciones=
            instrucciones,

        referencia_conversacion=
            referencia_conversacion,

        origen=
            "typebot_agenda_reserva_nlu",

        max_palabras=
            8,
    )


    nlu = _parse_nlu_reserva(
        interpretacion[
            "respuesta"
        ]
    )


    tipo = nlu[
        "tipo"
    ]


    if tipo == "FALTA_FECHA":

        return {
            "manejado":
                True,

            "accion":
                "agenda_reserva_falta_fecha",

            "respuesta":
                (
                    "Claro. ¿Para qué fecha quieres "
                    "agendar la cita?"
                ),

            "modelo":
                interpretacion["modelo"],

            "palabras_salida":
                interpretacion["palabras_salida"],

            "palabras_disponibles":
                interpretacion[
                    "palabras_disponibles"
                ],

            "fecha":
                "",

            "total_disponibles":
                0,

            "horarios":
                "",

            "cita_id":
                None,

            "estado":
                "",
        }


    if tipo == "FALTA_HORA":

        return {
            "manejado":
                True,

            "accion":
                "agenda_reserva_falta_hora",

            "respuesta":
                (
                    "Claro. ¿A qué hora quieres "
                    "agendar la cita?"
                ),

            "modelo":
                interpretacion["modelo"],

            "palabras_salida":
                interpretacion["palabras_salida"],

            "palabras_disponibles":
                interpretacion[
                    "palabras_disponibles"
                ],

            "fecha":
                "",

            "total_disponibles":
                0,

            "horarios":
                "",

            "cita_id":
                None,

            "estado":
                "",
        }


    if tipo in {
        "OTRO",
        "NO_INTERPRETADO",
    }:

        return {
            "manejado":
                False,
        }


    fecha = nlu[
        "fecha"
    ]

    hora = nlu[
        "hora"
    ]

    hora_texto = hora.strftime(
        "%H:%M"
    )


    try:

        slots_resultado = (
            listar_slots_disponibles(
                empresa=empresa,
                fecha=fecha,
            )
        )

    except GoogleCalendarCitasError:

        return {
            "manejado":
                True,

            "accion":
                "agenda_error",

            "respuesta":
                (
                    "No pude consultar la agenda "
                    "en este momento. Inténtalo nuevamente."
                ),

            "modelo":
                interpretacion["modelo"],

            "palabras_salida":
                interpretacion["palabras_salida"],

            "palabras_disponibles":
                interpretacion[
                    "palabras_disponibles"
                ],

            "fecha":
                fecha.isoformat(),

            "total_disponibles":
                0,

            "horarios":
                "",

            "cita_id":
                None,

            "estado":
                "",
        }


    slots = (
        slots_resultado.get(
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


    fecha_usuario = fecha.strftime(
        "%d/%m/%Y"
    )


    if hora_texto not in horas:

        alternativas = ", ".join(
            horas
        )


        if slots_resultado[
            "dia_cerrado"
        ]:

            respuesta = (
                f"El {fecha_usuario} no ofrecemos citas. "
                "Puedes indicarme otra fecha."
            )

        elif alternativas:

            respuesta = (
                f"El horario {hora_texto} no está disponible "
                f"el {fecha_usuario}. "
                f"Los horarios disponibles son: "
                f"{alternativas}."
            )

        else:

            respuesta = (
                f"No hay horarios disponibles el "
                f"{fecha_usuario}. "
                "Puedes indicarme otra fecha."
            )


        return {
            "manejado":
                True,

            "accion":
                "agenda_reserva_horario_no_disponible",

            "respuesta":
                respuesta,

            "modelo":
                interpretacion["modelo"],

            "palabras_salida":
                interpretacion["palabras_salida"],

            "palabras_disponibles":
                interpretacion[
                    "palabras_disponibles"
                ],

            "fecha":
                fecha.isoformat(),

            "total_disponibles":
                len(
                    horas
                ),

            "horarios":
                alternativas,

            "cita_id":
                None,

            "estado":
                "",
        }


    comando = (
        f"Confirmar cita "
        f"{fecha.isoformat()} "
        f"{hora_texto} "
        f"a nombre de TU NOMBRE"
    )


    respuesta = (
        f"El {fecha_usuario} a las {hora_texto} "
        "está disponible. "
        "Todavía no he creado la cita. "
        "Para confirmarla, selecciona "
        "“Hacer otra pregunta” y escribe exactamente: "
        f"{comando}. "
        "Reemplaza TU NOMBRE por tu nombre."
    )


    return {
        "manejado":
            True,

        "accion":
            "agenda_confirmacion_requerida",

        "respuesta":
            respuesta,

        "modelo":
            interpretacion[
                "modelo"
            ],

        "palabras_salida":
            interpretacion[
                "palabras_salida"
            ],

        "palabras_disponibles":
            interpretacion[
                "palabras_disponibles"
            ],

        "fecha":
            fecha.isoformat(),

        "total_disponibles":
            len(
                horas
            ),

        "horarios":
            ", ".join(
                horas
            ),

        "cita_id":
            None,

        "estado":
            "",
    }
