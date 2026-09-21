# =============================================================================
# TNL-GOOGLE-CALENDAR-CITAS-SERVICE-V1
# Servicio central de agenda/citas de NegocioListo.
# =============================================================================

from __future__ import annotations

from datetime import (
    datetime,
    timezone as dt_timezone,
)
from typing import Optional

from django.db import transaction
from django.utils import timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from core.models import (
    Bot,
    Cita,
    ConfiguracionGoogleCalendar,
    Empresa,
)

from core.services.google_calendar_oauth import (
    GOOGLE_CALENDAR_SCOPES,
    cifrar_token,
    descifrar_token,
    obtener_client_id,
    obtener_client_secret,
)


class GoogleCalendarCitasError(Exception):
    """Error controlado del servicio de citas."""


class GoogleCalendarNoConectadoError(
    GoogleCalendarCitasError
):
    pass


class GoogleCalendarHorarioOcupadoError(
    GoogleCalendarCitasError
):
    pass


class GoogleCalendarCitaNoEncontradaError(
    GoogleCalendarCitasError
):
    pass


def _obtener_configuracion(
    empresa: Empresa,
) -> ConfiguracionGoogleCalendar:

    config = (
        ConfiguracionGoogleCalendar.objects
        .filter(
            empresa=empresa
        )
        .first()
    )

    if config is None:
        raise GoogleCalendarNoConectadoError(
            "La empresa no tiene Google Calendar configurado."
        )

    if (
        config.estado_conexion
        !=
        ConfiguracionGoogleCalendar.ESTADO_CONECTADA
        or
        not config.habilitada
        or
        not config.calendar_id
        or
        not config.refresh_token_cifrado
    ):
        raise GoogleCalendarNoConectadoError(
            "Google Calendar no está conectado para esta empresa."
        )

    return config


# TNL-GOOGLE-CALENDAR-TOKEN-EXPIRY-V1
def _crear_credentials(
    config: ConfiguracionGoogleCalendar,
) -> Credentials:

    access_token = ""

    if config.access_token_cifrado:

        access_token = descifrar_token(
            config.access_token_cifrado
        )


    refresh_token = descifrar_token(
        config.refresh_token_cifrado
    )


    # google-auth trabaja internamente con
    # expiración UTC sin tzinfo. Django devuelve
    # DateTimeField aware cuando USE_TZ=True.
    expiry = (
        config.token_expira_en
    )


    if (
        expiry is not None
        and
        timezone.is_aware(
            expiry
        )
    ):

        expiry = (
            expiry
            .astimezone(
                dt_timezone.utc
            )
            .replace(
                tzinfo=None
            )
        )


    return Credentials(
        token=access_token or None,
        refresh_token=refresh_token,
        token_uri=
            "https://oauth2.googleapis.com/token",
        client_id=obtener_client_id(),
        client_secret=obtener_client_secret(),
        scopes=list(
            GOOGLE_CALENDAR_SCOPES
        ),
        expiry=expiry,
    )


def _persistir_token_refrescado(
    config: ConfiguracionGoogleCalendar,
    credentials: Credentials,
) -> None:

    campos = []

    if credentials.token:

        config.access_token_cifrado = (
            cifrar_token(
                credentials.token
            )
        )

        campos.append(
            "access_token_cifrado"
        )

    if credentials.expiry is not None:

        # TNL-GOOGLE-CALENDAR-TOKEN-EXPIRY-SAVE-V1
        expiry = (
            credentials.expiry
        )

        # google-auth entrega normalmente expiry
        # como UTC naive; Django con USE_TZ=True
        # debe almacenar un datetime aware.
        if timezone.is_naive(
            expiry
        ):

            expiry = (
                timezone.make_aware(
                    expiry,
                    dt_timezone.utc,
                )
            )

        config.token_expira_en = (
            expiry
        )

        campos.append(
            "token_expira_en"
        )

    if credentials.refresh_token:

        config.refresh_token_cifrado = (
            cifrar_token(
                credentials.refresh_token
            )
        )

        campos.append(
            "refresh_token_cifrado"
        )

    if campos:

        campos.append(
            "actualizado_en"
        )

        config.save(
            update_fields=campos
        )


def _obtener_credentials_validas(
    config: ConfiguracionGoogleCalendar,
) -> Credentials:

    credentials = (
        _crear_credentials(
            config
        )
    )

    necesita_refresh = bool(
        not credentials.token
        or
        credentials.expired
    )

    if necesita_refresh:

        try:

            credentials.refresh(
                Request()
            )

        except Exception as exc:

            raise GoogleCalendarCitasError(
                "No fue posible renovar la autorización de Google Calendar."
            ) from exc

        _persistir_token_refrescado(
            config,
            credentials,
        )

    return credentials


def _crear_servicio_calendar(
    config: ConfiguracionGoogleCalendar,
):

    credentials = (
        _obtener_credentials_validas(
            config
        )
    )

    return build(
        "calendar",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )


# TNL-CITA-LOCAL-LOCK-RUNTIME-V1
# TNL-CITA-PAYMENT-WIRING-V1
from core.services.cita_payment import (
    citas_bloqueantes_queryset,
    hay_bloqueo_local_cita,
    resolver_pago_cita,
)


def consultar_disponibilidad(
    *,
    empresa: Empresa,
    inicio: datetime,
    fin: datetime,
) -> dict:

    if inicio is None or fin is None:
        raise GoogleCalendarCitasError(
            "Inicio y fin son obligatorios."
        )

    if fin <= inicio:
        raise GoogleCalendarCitasError(
            "La fecha final debe ser posterior al inicio."
        )

    if timezone.is_naive(inicio):
        raise GoogleCalendarCitasError(
            "La fecha de inicio debe incluir zona horaria."
        )

    if timezone.is_naive(fin):
        raise GoogleCalendarCitasError(
            "La fecha final debe incluir zona horaria."
        )

    config = _obtener_configuracion(
        empresa
    )

    service = _crear_servicio_calendar(
        config
    )

    try:

        response = (
            service
            .freebusy()
            .query(
                body={
                    "timeMin":
                        inicio.isoformat(),

                    "timeMax":
                        fin.isoformat(),

                    "timeZone":
                        config.zona_horaria,

                    "items": [
                        {
                            "id":
                                config.calendar_id
                        }
                    ],
                }
            )
            .execute()
        )

    except HttpError as exc:

        raise GoogleCalendarCitasError(
            "Google Calendar no pudo consultar disponibilidad."
        ) from exc

    data = (
        response
        .get(
            "calendars",
            {}
        )
        .get(
            config.calendar_id,
            {}
        )
    )

    errors = (
        data.get(
            "errors",
            []
        )
        or []
    )

    if errors:
        raise GoogleCalendarCitasError(
            "Google Calendar devolvió un error al consultar disponibilidad."
        )

    busy = (
        data.get(
            "busy",
            []
        )
        or []
    )

    return {
        "disponible":
            not bool(busy),

        "ocupados":
            busy,

        "calendar_id":
            config.calendar_id,

        "zona_horaria":
            config.zona_horaria,
    }


def crear_cita(
    *,
    empresa: Empresa,
    inicio: datetime,
    fin: datetime,
    titulo: str,
    nombre_cliente: str = "",
    telefono_cliente: str = "",
    email_cliente: str = "",
    servicio: str = "",
    servicio_producto=None,
    descripcion: str = "",
    referencia_conversacion: str = "",
    bot: Optional[Bot] = None,
    origen: str = Cita.ORIGEN_CHATBOT,
) -> Cita:

    titulo = str(
        titulo or ""
    ).strip()

    if not titulo:
        raise GoogleCalendarCitasError(
            "El título de la cita es obligatorio."
        )

    if origen not in {
        value
        for value, _label
        in Cita.ORIGENES
    }:
        raise GoogleCalendarCitasError(
            "Origen de cita inválido."
        )

    if bot is not None:

        if bot.empresa_id != empresa.pk:
            raise GoogleCalendarCitasError(
                "El bot no pertenece a esta empresa."
            )

    disponibilidad = (
        consultar_slot_agenda(
            empresa=empresa,
            inicio=inicio,
            fin=fin,
        )
    )

    if not disponibilidad[
        "disponible"
    ]:
        raise GoogleCalendarHorarioOcupadoError(
            "El horario solicitado no está disponible."
        )

    config = _obtener_configuracion(
        empresa
    )

    # TNL-CITA-PAYMENT-CREATE-V1
    try:
        pago_cita = resolver_pago_cita(
            empresa=empresa,
            servicio_producto=
                servicio_producto,
        )
    except ValueError as exc:
        raise GoogleCalendarCitasError(
            str(exc)
        ) from exc


    def crear_registro(
        valores_pago,
    ):
        return Cita.objects.create(
            empresa=empresa,
            bot=bot,
            estado=
                Cita.ESTADO_PENDIENTE_CONFIRMACION,
            origen=origen,
            nombre_cliente=
                str(nombre_cliente or "").strip(),
            telefono_cliente=
                str(telefono_cliente or "").strip(),
            email_cliente=
                str(email_cliente or "").strip(),
            servicio=(
                valores_pago["servicio"]
                or
                str(servicio or "").strip()
            ),
            servicio_producto=
                valores_pago[
                    "servicio_producto"
                ],
            titulo=titulo,
            descripcion=
                str(descripcion or "").strip(),
            inicio=inicio,
            fin=fin,
            zona_horaria=
                config.zona_horaria,
            politica_pago_aplicada=
                valores_pago["politica"],
            importe_total=
                valores_pago["importe_total"],
            moneda=
                valores_pago["moneda"],
            porcentaje_pago_requerido=
                valores_pago[
                    "porcentaje_pago_requerido"
                ],
            importe_pago_requerido=
                valores_pago[
                    "importe_pago_requerido"
                ],
            retencion_pago_hasta=
                valores_pago[
                    "retencion_pago_hasta"
                ],
            referencia_conversacion=
                str(
                    referencia_conversacion
                    or
                    ""
                ).strip(),
        )


    if pago_cita["requiere_pago"]:

        # TNL-CITA-PAYMENT-CONFIG-IMPORT-V1
        from core.models import ConfiguracionAgenda

        with transaction.atomic():

            agenda_lock = (
                ConfiguracionAgenda.objects
                .select_for_update()
                .filter(
                    empresa=empresa
                )
                .first()
            )

            if agenda_lock is None:
                raise GoogleCalendarCitasError(
                    "La configuración de agenda no existe."
                )


            try:
                pago_cita = resolver_pago_cita(
                    empresa=empresa,
                    servicio_producto=
                        servicio_producto,
                )
            except ValueError as exc:
                raise GoogleCalendarCitasError(
                    str(exc)
                ) from exc


            if not pago_cita["requiere_pago"]:
                raise GoogleCalendarCitasError(
                    "La política de pago cambió durante la reservación."
                )


            if hay_bloqueo_local_cita(
                empresa=empresa,
                inicio=inicio,
                fin=fin,
            ):
                raise GoogleCalendarHorarioOcupadoError(
                    "El horario solicitado ya está reservado."
                )


            cita = crear_registro(
                pago_cita
            )


        # Importante:
        # una cita que requiere pago NO llega
        # todavía a events().insert().
        return cita


    cita = crear_registro(
        pago_cita
    )

    service = _crear_servicio_calendar(
        config
    )

    evento_body = {
        "summary":
            cita.titulo,

        "description":
            cita.descripcion,

        "start": {
            "dateTime":
                cita.inicio.isoformat(),

            "timeZone":
                config.zona_horaria,
        },

        "end": {
            "dateTime":
                cita.fin.isoformat(),

            "timeZone":
                config.zona_horaria,
        },
    }

    try:

        evento = (
            service
            .events()
            .insert(
                calendarId=
                    config.calendar_id,

                body=
                    evento_body,

                sendUpdates=
                    "none",
            )
            .execute()
        )

        event_id = str(
            evento.get(
                "id"
            )
            or
            ""
        ).strip()

        if not event_id:

            raise GoogleCalendarCitasError(
                "Google Calendar no devolvió un identificador del evento."
            )

        with transaction.atomic():

            cita_actual = (
                Cita.objects
                .select_for_update()
                .get(
                    pk=cita.pk,
                    empresa=empresa,
                )
            )

            cita_actual.estado = (
                Cita.ESTADO_PROGRAMADA
            )

            cita_actual.google_calendar_id = (
                config.calendar_id
            )

            cita_actual.google_event_id = (
                event_id
            )

            cita_actual.google_event_etag = str(
                evento.get(
                    "etag"
                )
                or
                ""
            )

            cita_actual.google_html_link = str(
                evento.get(
                    "htmlLink"
                )
                or
                ""
            )

            cita_actual.confirmada_en = (
                timezone.now()
            )

            cita_actual.google_sincronizada_en = (
                timezone.now()
            )

            cita_actual.ultimo_error = ""

            cita_actual.save()

            cita = cita_actual

    except Exception as exc:

        Cita.objects.filter(
            pk=cita.pk,
            empresa=empresa,
        ).update(
            estado=
                Cita.ESTADO_ERROR,

            ultimo_error=
                type(exc).__name__,
        )

        raise GoogleCalendarCitasError(
            "No fue posible crear la cita en Google Calendar."
        ) from exc

    return cita


# TNL-CITA-PAID-GOOGLE-FINALIZE-V1
def programar_cita_pagada_en_google(
    cita_id,
) -> Cita:
    """
    Finaliza en Google Calendar una Cita ya existente
    cuyo pago requerido ya fue confirmado.

    No crea una nueva Cita.

    Las llamadas remotas a Google se realizan fuera
    de transaction.atomic().
    """

    try:
        cita_id = int(
            cita_id
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise GoogleCalendarCitasError(
            "El identificador de la cita no es válido."
        ) from exc

    # -------------------------------------------------------------
    # Snapshot corto y protegido.
    # Ninguna llamada remota ocurre dentro de este atomic().
    # -------------------------------------------------------------
    with transaction.atomic():

        try:
            cita = (
                Cita.objects
                .select_related(
                    "empresa"
                )
                .select_for_update()
                .get(
                    pk=cita_id
                )
            )

        except Cita.DoesNotExist as exc:
            raise GoogleCalendarCitasError(
                "La cita no existe."
            ) from exc

        # Idempotencia local.
        if cita.google_event_id:
            return cita

        if cita.estado in {
            Cita.ESTADO_CANCELADA,
            Cita.ESTADO_COMPLETADA,
        }:
            raise GoogleCalendarCitasError(
                "La cita ya no admite programación en Google Calendar."
            )

        if cita.politica_pago_aplicada not in {
            "anticipo",
            "pago_completo",
        }:
            raise GoogleCalendarCitasError(
                "La cita no corresponde a una reservación con pago."
            )

        if cita.pago_confirmado_en is None:
            raise GoogleCalendarCitasError(
                "La cita todavía no tiene un pago confirmado."
            )

        if (
            cita.importe_pago_requerido <= 0
            or
            cita.importe_pagado
            <
            cita.importe_pago_requerido
        ):
            raise GoogleCalendarCitasError(
                "El importe pagado no cubre el importe requerido."
            )

        empresa = cita.empresa
        empresa_id = cita.empresa_id

        inicio = cita.inicio
        fin = cita.fin

        titulo = cita.titulo
        descripcion = cita.descripcion

        # ID permitido por Google:
        # sólo letras a-v y dígitos.
        #
        # Al depender del PK global de Cita es estable
        # para reintentos del mismo registro.
        evento_id_objetivo = (
            f"tnlcita{cita.pk}"
        )

    # -------------------------------------------------------------
    # A partir de aquí NO existe transaction.atomic() abierto
    # por este helper.
    # -------------------------------------------------------------

    def marcar_error(
        exc,
    ):
        (
            Cita.objects
            .filter(
                pk=cita_id,
                empresa_id=empresa_id,
                google_event_id="",
            )
            .exclude(
                estado__in={
                    Cita.ESTADO_CANCELADA,
                    Cita.ESTADO_COMPLETADA,
                }
            )
            .update(
                estado=
                    Cita.ESTADO_ERROR,
                ultimo_error=
                    type(exc).__name__,
            )
        )

    def status_http(
        exc,
    ):
        return getattr(
            getattr(
                exc,
                "resp",
                None,
            ),
            "status",
            None,
        )

    def obtener_evento_existente(
        service,
        config,
    ):
        try:
            return (
                service
                .events()
                .get(
                    calendarId=
                        config.calendar_id,
                    eventId=
                        evento_id_objetivo,
                )
                .execute()
            )

        except HttpError as exc:
            if status_http(
                exc
            ) == 404:
                return None

            raise

    try:
        config = _obtener_configuracion(
            empresa
        )

        # ---------------------------------------------------------
        # 1. Conflicto local.
        #
        # La propia Cita pagada debe excluirse del bloqueo.
        # Una retención vencida ajena ya será evaluada por
        # cita_payment usando "ahora".
        # ---------------------------------------------------------
        if hay_bloqueo_local_cita(
            empresa=empresa,
            inicio=inicio,
            fin=fin,
            ahora=timezone.now(),
            excluir_cita_id=cita_id,
        ):
            raise GoogleCalendarHorarioOcupadoError(
                "El horario ya está ocupado por otra cita."
            )

        # ---------------------------------------------------------
        # 2. Ocupación real Google.
        #
        # No usamos consultar_slot_agenda() porque esta Cita
        # ya pasó las reglas comerciales cuando fue creada.
        # ---------------------------------------------------------
        google_resultado = (
            consultar_disponibilidad(
                empresa=empresa,
                inicio=inicio,
                fin=fin,
            )
        )

        evento = None
        service = None

        if not bool(
            google_resultado[
                "disponible"
            ]
        ):
            # Puede ser un evento nuestro creado en un intento
            # anterior que alcanzó Google pero no alcanzó a
            # persistirse localmente.
            service = _crear_servicio_calendar(
                config
            )

            evento = obtener_evento_existente(
                service,
                config,
            )

            if evento is None:
                raise GoogleCalendarHorarioOcupadoError(
                    "El horario ya está ocupado en Google Calendar."
                )

        else:
            service = _crear_servicio_calendar(
                config
            )

            evento_body = {
                "id":
                    evento_id_objetivo,

                "summary":
                    titulo,

                "description":
                    descripcion,

                "start": {
                    "dateTime":
                        inicio.isoformat(),

                    "timeZone":
                        config.zona_horaria,
                },

                "end": {
                    "dateTime":
                        fin.isoformat(),

                    "timeZone":
                        config.zona_horaria,
                },
            }

            try:
                evento = (
                    service
                    .events()
                    .insert(
                        calendarId=
                            config.calendar_id,

                        body=
                            evento_body,

                        sendUpdates=
                            "none",
                    )
                    .execute()
                )

            except HttpError as exc:
                # Otro intento concurrente pudo haber creado
                # exactamente el mismo ID determinista.
                if status_http(
                    exc
                ) != 409:
                    raise

                evento = obtener_evento_existente(
                    service,
                    config,
                )

                if evento is None:
                    raise

        event_id = str(
            (
                evento
                or {}
            ).get(
                "id"
            )
            or
            ""
        ).strip()

        if not event_id:
            raise GoogleCalendarCitasError(
                "Google Calendar no devolvió un identificador del evento."
            )

        # ---------------------------------------------------------
        # 3. Persistencia local final.
        #
        # Google ya terminó antes de abrir esta transacción.
        # ---------------------------------------------------------
        with transaction.atomic():

            cita_actual = (
                Cita.objects
                .select_for_update()
                .get(
                    pk=cita_id,
                    empresa_id=empresa_id,
                )
            )

            # Otro finalizador pudo haber terminado mientras
            # estábamos fuera de PostgreSQL.
            if cita_actual.google_event_id:
                return cita_actual

            if cita_actual.estado in {
                Cita.ESTADO_CANCELADA,
                Cita.ESTADO_COMPLETADA,
            }:
                raise GoogleCalendarCitasError(
                    "La cita cambió de estado durante la programación."
                )

            cita_actual.estado = (
                Cita.ESTADO_PROGRAMADA
            )

            cita_actual.google_calendar_id = (
                config.calendar_id
            )

            cita_actual.google_event_id = (
                event_id
            )

            cita_actual.google_event_etag = str(
                (
                    evento
                    or {}
                ).get(
                    "etag"
                )
                or
                ""
            )

            cita_actual.google_html_link = str(
                (
                    evento
                    or {}
                ).get(
                    "htmlLink"
                )
                or
                ""
            )

            cita_actual.confirmada_en = (
                timezone.now()
            )

            cita_actual.google_sincronizada_en = (
                timezone.now()
            )

            cita_actual.ultimo_error = ""

            cita_actual.save()

            return cita_actual

    except GoogleCalendarHorarioOcupadoError as exc:
        marcar_error(
            exc
        )
        raise

    except GoogleCalendarCitasError as exc:
        marcar_error(
            exc
        )
        raise

    except Exception as exc:
        marcar_error(
            exc
        )

        raise GoogleCalendarCitasError(
            "No fue posible programar la cita pagada en Google Calendar."
        ) from exc


def cancelar_cita(
    *,
    empresa: Empresa,
    cita_id: int,
) -> Cita:

    config = _obtener_configuracion(
        empresa
    )

    cita = (
        Cita.objects
        .filter(
            pk=cita_id,
            empresa=empresa,
        )
        .first()
    )

    if cita is None:
        raise GoogleCalendarCitaNoEncontradaError(
            "La cita no existe para esta empresa."
        )

    if cita.estado == Cita.ESTADO_CANCELADA:
        return cita

    if not cita.google_event_id:

        raise GoogleCalendarCitasError(
            "La cita no tiene un evento Google asociado."
        )

    service = _crear_servicio_calendar(
        config
    )

    try:

        (
            service
            .events()
            .delete(
                calendarId=
                    cita.google_calendar_id
                    or
                    config.calendar_id,

                eventId=
                    cita.google_event_id,

                sendUpdates=
                    "none",
            )
            .execute()
        )

    except HttpError as exc:

        status = getattr(
            getattr(
                exc,
                "resp",
                None,
            ),
            "status",
            None,
        )

        # Si el evento ya no existe en Google,
        # consideramos la cancelación idempotente.
        if status not in {
            404,
            410,
        }:
            raise GoogleCalendarCitasError(
                "No fue posible cancelar el evento en Google Calendar."
            ) from exc

    with transaction.atomic():

        cita = (
            Cita.objects
            .select_for_update()
            .get(
                pk=cita.pk,
                empresa=empresa,
            )
        )

        cita.estado = (
            Cita.ESTADO_CANCELADA
        )

        cita.cancelada_en = (
            timezone.now()
        )

        cita.google_sincronizada_en = (
            timezone.now()
        )

        cita.ultimo_error = ""

        cita.save()

    return cita


# =============================================================================
# TNL-AGENDA-SLOTS-SERVICE-V1
#
# Motor central de horarios ofertables.
#
# Autoridades:
#   1. ConfiguracionAgenda / HorarioAtencion:
#      cuándo la empresa permite citas.
#   2. Google Calendar FreeBusy:
#      qué intervalos están realmente ocupados.
#
# No crea eventos.
# No modifica Cita.
# =============================================================================


def listar_slots_disponibles(
    *,
    empresa,
    fecha,
    duracion_minutos=None,
    hora_desde=None,
    hora_hasta=None,
):
    """
    Devuelve slots realmente disponibles para una fecha local.

    hora_desde:
        si existe, sólo ofrece slots cuyo inicio sea >= hora_desde.

    hora_hasta:
        si existe, sólo ofrece slots cuyo fin sea <= hora_hasta.

    Hace como máximo una consulta FreeBusy a Google por fecha.
    Si el día está cerrado, no llama Google.
    """

    from datetime import (
        date as date_type,
        datetime,
        time as time_type,
        timedelta,
        timezone as datetime_timezone,
    )

    from zoneinfo import (
        ZoneInfo,
        ZoneInfoNotFoundError,
    )

    from django.utils import timezone

    from core.models import (
        ConfiguracionAgenda,
        HorarioAtencion,
    )


    # -----------------------------------------------------------------
    # Validaciones de entrada.
    # -----------------------------------------------------------------

    if not isinstance(
        fecha,
        date_type,
    ) or isinstance(
        fecha,
        datetime,
    ):
        raise GoogleCalendarCitasError(
            "La fecha de agenda debe ser una fecha válida."
        )


    if (
        hora_desde is not None
        and
        not isinstance(
            hora_desde,
            time_type,
        )
    ):
        raise GoogleCalendarCitasError(
            "hora_desde debe ser una hora válida."
        )


    if (
        hora_hasta is not None
        and
        not isinstance(
            hora_hasta,
            time_type,
        )
    ):
        raise GoogleCalendarCitasError(
            "hora_hasta debe ser una hora válida."
        )


    if (
        hora_desde is not None
        and
        hora_hasta is not None
        and
        hora_hasta
        <=
        hora_desde
    ):
        raise GoogleCalendarCitasError(
            "hora_hasta debe ser posterior a hora_desde."
        )


    # -----------------------------------------------------------------
    # Configuración comercial de agenda.
    # -----------------------------------------------------------------

    try:

        config_agenda = (
            ConfiguracionAgenda.objects
            .get(
                empresa=empresa
            )
        )

    except ConfiguracionAgenda.DoesNotExist as exc:

        raise GoogleCalendarCitasError(
            "La empresa no tiene configurada su agenda de atención."
        ) from exc


    try:

        config_google = (
            _obtener_configuracion(
                empresa
            )
        )

    except Exception:
        raise


    try:

        zona = ZoneInfo(
            config_google.zona_horaria
        )

    except ZoneInfoNotFoundError as exc:

        raise GoogleCalendarCitasError(
            "La zona horaria configurada no es válida."
        ) from exc


    if duracion_minutos is None:

        duracion = int(
            config_agenda
            .duracion_predeterminada_minutos
        )

    else:

        if isinstance(
            duracion_minutos,
            bool,
        ):
            raise GoogleCalendarCitasError(
                "La duración debe ser un número entero."
            )

        try:
            duracion = int(
                duracion_minutos
            )
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise GoogleCalendarCitasError(
                "La duración debe ser un número entero."
            ) from exc


    intervalo = int(
        config_agenda.intervalo_slots_minutos
    )

    anticipacion = int(
        config_agenda.anticipacion_minima_minutos
    )


    if not (
        1
        <= duracion
        <= 1440
    ):
        raise GoogleCalendarCitasError(
            "La duración debe estar entre 1 y 1440 minutos."
        )


    if not (
        1
        <= intervalo
        <= 1440
    ):
        raise GoogleCalendarCitasError(
            "El intervalo de slots debe estar entre 1 y 1440 minutos."
        )


    if anticipacion < 0:
        raise GoogleCalendarCitasError(
            "La anticipación mínima no puede ser negativa."
        )


    # -----------------------------------------------------------------
    # Bloques de atención del día.
    # Domingo sin registros => día cerrado.
    # -----------------------------------------------------------------

    bloques = list(
        HorarioAtencion.objects
        .filter(
            empresa=empresa,
            dia_semana=fecha.weekday(),
            activo=True,
        )
        .order_by(
            "hora_inicio"
        )
    )


    bloques_serializados = [
        {
            "inicio":
                x.hora_inicio.strftime(
                    "%H:%M"
                ),
            "fin":
                x.hora_fin.strftime(
                    "%H:%M"
                ),
        }
        for x in bloques
    ]


    if not bloques:

        return {
            "fecha":
                fecha.isoformat(),

            "dia_semana":
                fecha.weekday(),

            "dia_cerrado":
                True,

            "zona_horaria":
                config_google.zona_horaria,

            "duracion_minutos":
                duracion,

            "intervalo_minutos":
                intervalo,

            "anticipacion_minima_minutos":
                anticipacion,

            "bloques_atencion":
                [],

            "bloques_ocupados_google":
                0,

            "total_candidatos":
                0,

            "descartados_anticipacion":
                0,

            "descartados_google":
                0,

            "total_disponibles":
                0,

            "slots":
                [],
        }


    # -----------------------------------------------------------------
    # Localización horaria segura, incluyendo zonas con DST.
    # -----------------------------------------------------------------

    def localizar(
        fecha_local,
        hora_local,
    ):

        naive = datetime.combine(
            fecha_local,
            hora_local,
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
                "Un horario configurado no existe por un cambio de zona horaria."
            )


        offsets = {
            candidato.utcoffset()
            for candidato in candidatos
        }


        if len(offsets) > 1:

            raise GoogleCalendarCitasError(
                "Un horario configurado es ambiguo por un cambio de zona horaria."
            )


        return candidatos[0]


    # -----------------------------------------------------------------
    # Construcción de candidatos comerciales.
    # -----------------------------------------------------------------

    ahora_local = (
        timezone.now()
        .astimezone(
            zona
        )
    )

    corte_anticipacion = (
        ahora_local
        +
        timedelta(
            minutes=
                anticipacion
        )
    )


    candidatos = []

    descartados_anticipacion = 0


    for bloque in bloques:

        inicio_bloque = localizar(
            fecha,
            bloque.hora_inicio,
        )

        fin_bloque = localizar(
            fecha,
            bloque.hora_fin,
        )

        actual = inicio_bloque


        while (
            actual
            +
            timedelta(
                minutes=
                    duracion
            )
            <=
            fin_bloque
        ):

            fin_slot = (
                actual
                +
                timedelta(
                    minutes=
                        duracion
                )
            )


            # Filtro "después de..."
            if (
                hora_desde is not None
                and
                actual.timetz().replace(
                    tzinfo=None
                )
                <
                hora_desde
            ):

                actual += timedelta(
                    minutes=
                        intervalo
                )

                continue


            # Filtro "antes de..."
            if (
                hora_hasta is not None
                and
                fin_slot.timetz().replace(
                    tzinfo=None
                )
                >
                hora_hasta
            ):

                actual += timedelta(
                    minutes=
                        intervalo
                )

                continue


            if actual < corte_anticipacion:

                descartados_anticipacion += 1

                actual += timedelta(
                    minutes=
                        intervalo
                )

                continue


            candidatos.append(
                (
                    actual,
                    fin_slot,
                )
            )


            actual += timedelta(
                minutes=
                    intervalo
            )


    if not candidatos:

        return {
            "fecha":
                fecha.isoformat(),

            "dia_semana":
                fecha.weekday(),

            "dia_cerrado":
                False,

            "zona_horaria":
                config_google.zona_horaria,

            "duracion_minutos":
                duracion,

            "intervalo_minutos":
                intervalo,

            "anticipacion_minima_minutos":
                anticipacion,

            "bloques_atencion":
                bloques_serializados,

            "bloques_ocupados_google":
                0,

            "total_candidatos":
                0,

            "descartados_anticipacion":
                descartados_anticipacion,

            "descartados_google":
                0,

            "total_disponibles":
                0,

            "slots":
                [],
        }


    # -----------------------------------------------------------------
    # UNA sola consulta Google FreeBusy para cubrir todos los candidatos.
    # -----------------------------------------------------------------

    ventana_inicio = min(
        x[0]
        for x in candidatos
    )

    ventana_fin = max(
        x[1]
        for x in candidatos
    )


    disponibilidad = (
        consultar_disponibilidad(
            empresa=empresa,
            inicio=ventana_inicio,
            fin=ventana_fin,
        )
    )


    ocupados_raw = (
        disponibilidad.get(
            "ocupados"
        )
        or []
    )


    def parse_rfc3339(
        value,
    ):

        texto = str(
            value or ""
        ).strip()

        if not texto:
            raise GoogleCalendarCitasError(
                "Google Calendar devolvió un bloque ocupado inválido."
            )

        try:

            parsed = datetime.fromisoformat(
                texto.replace(
                    "Z",
                    "+00:00",
                )
            )

        except ValueError as exc:

            raise GoogleCalendarCitasError(
                "Google Calendar devolvió una fecha ocupada inválida."
            ) from exc


        if parsed.tzinfo is None:

            raise GoogleCalendarCitasError(
                "Google Calendar devolvió un horario ocupado sin zona horaria."
            )


        return parsed


    ocupados = []


    for bloque in ocupados_raw:

        busy_inicio = parse_rfc3339(
            bloque.get(
                "start"
            )
        )

        busy_fin = parse_rfc3339(
            bloque.get(
                "end"
            )
        )


        if busy_fin <= busy_inicio:
            continue


        ocupados.append(
            (
                busy_inicio,
                busy_fin,
            )
        )


    # -----------------------------------------------------------------
    # TNL-CITA-LOCAL-LOCK-SLOTS-V1
    # Cargar una sola vez los bloqueos locales de toda la ventana.
    # -----------------------------------------------------------------

    ocupados_local = list(
        citas_bloqueantes_queryset(
            empresa=empresa,
            inicio=ventana_inicio,
            fin=ventana_fin,
        )
        .values_list(
            "inicio",
            "fin",
        )
    )


    # -----------------------------------------------------------------
    # Eliminar slots ocupados localmente o por Google.
    #
    # [slot_inicio, slot_fin)
    # [busy_inicio, busy_fin)
    #
    # Hay traslape cuando:
    #   slot_inicio < busy_fin
    #   AND
    #   slot_fin > busy_inicio
    # -----------------------------------------------------------------

    slots = []

    descartados_google = 0


    for (
        inicio_slot,
        fin_slot,
    ) in candidatos:

        ocupado_local = any(
            (
                inicio_slot < local_fin
                and
                fin_slot > local_inicio
            )
            for (
                local_inicio,
                local_fin,
            )
            in ocupados_local
        )

        if ocupado_local:
            continue


        ocupado = any(
            (
                inicio_slot
                <
                busy_fin
                and
                fin_slot
                >
                busy_inicio
            )
            for (
                busy_inicio,
                busy_fin,
            )
            in ocupados
        )


        if ocupado:

            descartados_google += 1
            continue


        slots.append(
            {
                "hora":
                    inicio_slot.strftime(
                        "%H:%M"
                    ),

                "hora_fin":
                    fin_slot.strftime(
                        "%H:%M"
                    ),

                "inicio":
                    inicio_slot.isoformat(),

                "fin":
                    fin_slot.isoformat(),
            }
        )


    return {
        "fecha":
            fecha.isoformat(),

        "dia_semana":
            fecha.weekday(),

        "dia_cerrado":
            False,

        "zona_horaria":
            config_google.zona_horaria,

        "duracion_minutos":
            duracion,

        "intervalo_minutos":
            intervalo,

        "anticipacion_minima_minutos":
            anticipacion,

        "bloques_atencion":
            bloques_serializados,

        "bloques_ocupados_google":
            len(
                ocupados
            ),

        "total_candidatos":
            len(
                candidatos
            ),

        "descartados_anticipacion":
            descartados_anticipacion,

        "descartados_google":
            descartados_google,

        "total_disponibles":
            len(
                slots
            ),

        "slots":
            slots,
    }


# =============================================================================
# TNL-AGENDA-SLOT-VALIDATION-V1
#
# Validador central de un horario concreto.
#
# Se usa tanto para:
#   - consultar disponibilidad;
#   - crear una cita.
#
# De esta manera un consumidor directo de la API no puede saltarse:
#   - horario comercial;
#   - cortes/comida;
#   - intervalo de slots;
#   - anticipación mínima.
#
# Google Calendar continúa siendo autoridad para ocupación real.
# =============================================================================


def consultar_slot_agenda(
    *,
    empresa,
    inicio,
    fin,
):
    from datetime import (
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
        ConfiguracionAgenda,
        HorarioAtencion,
    )


    # -----------------------------------------------------------------
    # Fechas válidas y aware.
    # -----------------------------------------------------------------

    if inicio is None or fin is None:

        raise GoogleCalendarCitasError(
            "Inicio y fin son obligatorios."
        )


    if timezone.is_naive(
        inicio
    ):

        raise GoogleCalendarCitasError(
            "La fecha de inicio debe incluir zona horaria."
        )


    if timezone.is_naive(
        fin
    ):

        raise GoogleCalendarCitasError(
            "La fecha final debe incluir zona horaria."
        )


    if fin <= inicio:

        raise GoogleCalendarCitasError(
            "La fecha final debe ser posterior al inicio."
        )


    # -----------------------------------------------------------------
    # Configuración.
    # -----------------------------------------------------------------

    try:

        agenda = (
            ConfiguracionAgenda.objects
            .get(
                empresa=empresa
            )
        )

    except ConfiguracionAgenda.DoesNotExist as exc:

        raise GoogleCalendarCitasError(
            "La empresa no tiene configurada su agenda de atención."
        ) from exc


    google = _obtener_configuracion(
        empresa
    )


    try:

        zona = ZoneInfo(
            google.zona_horaria
        )

    except ZoneInfoNotFoundError as exc:

        raise GoogleCalendarCitasError(
            "La zona horaria configurada no es válida."
        ) from exc


    inicio_local = inicio.astimezone(
        zona
    )

    fin_local = fin.astimezone(
        zona
    )


    # No permitimos una cita comercial que atraviese
    # dos fechas locales.
    if (
        inicio_local.date()
        !=
        fin_local.date()
    ):

        return {
            "disponible": False,
            "motivo":
                "fuera_horario",
            "ocupados": [],
            "calendar_id":
                google.calendar_id,
            "zona_horaria":
                google.zona_horaria,
            "reglas_agenda":
                True,
        }


    # -----------------------------------------------------------------
    # Anticipación mínima.
    # -----------------------------------------------------------------

    corte = (
        timezone.now()
        .astimezone(
            zona
        )
        +
        timedelta(
            minutes=
                int(
                    agenda
                    .anticipacion_minima_minutos
                )
        )
    )


    if inicio_local < corte:

        return {
            "disponible": False,
            "motivo":
                "anticipacion_minima",
            "ocupados": [],
            "calendar_id":
                google.calendar_id,
            "zona_horaria":
                google.zona_horaria,
            "reglas_agenda":
                True,
        }


    # -----------------------------------------------------------------
    # Horarios comerciales del día.
    # -----------------------------------------------------------------

    bloques = list(
        HorarioAtencion.objects
        .filter(
            empresa=empresa,
            dia_semana=
                inicio_local.date().weekday(),
            activo=True,
        )
        .order_by(
            "hora_inicio"
        )
    )


    if not bloques:

        return {
            "disponible": False,
            "motivo":
                "dia_cerrado",
            "ocupados": [],
            "calendar_id":
                google.calendar_id,
            "zona_horaria":
                google.zona_horaria,
            "reglas_agenda":
                True,
        }


    # -----------------------------------------------------------------
    # Localización segura para zonas con DST.
    # -----------------------------------------------------------------

    def localizar(
        fecha_local,
        hora_local,
    ):

        naive = datetime.combine(
            fecha_local,
            hora_local,
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
                "Un horario configurado no existe por un cambio de zona horaria."
            )


        offsets = {
            candidato.utcoffset()
            for candidato in candidatos
        }


        if len(offsets) > 1:

            raise GoogleCalendarCitasError(
                "Un horario configurado es ambiguo por un cambio de zona horaria."
            )


        return candidatos[0]


    intervalo_segundos = (
        int(
            agenda.intervalo_slots_minutos
        )
        *
        60
    )


    slot_comercial_valido = False


    for bloque in bloques:

        bloque_inicio = localizar(
            inicio_local.date(),
            bloque.hora_inicio,
        )

        bloque_fin = localizar(
            inicio_local.date(),
            bloque.hora_fin,
        )


        # Debe quedar completamente dentro
        # de un único bloque. Esto impide
        # atravesar comida/cortes.
        if not (
            inicio_local
            >=
            bloque_inicio
            and
            fin_local
            <=
            bloque_fin
        ):

            continue


        desplazamiento = (
            inicio_local
            -
            bloque_inicio
        ).total_seconds()


        # El inicio debe caer exactamente en
        # la malla de slots configurada.
        if (
            desplazamiento < 0
            or
            desplazamiento
            %
            intervalo_segundos
            !=
            0
        ):

            continue


        slot_comercial_valido = True
        break


    if not slot_comercial_valido:

        return {
            "disponible": False,
            "motivo":
                "fuera_horario_o_intervalo",
            "ocupados": [],
            "calendar_id":
                google.calendar_id,
            "zona_horaria":
                google.zona_horaria,
            "reglas_agenda":
                True,
        }


    # -----------------------------------------------------------------
    # Sólo después de pasar las reglas locales
    # consultamos Google.
    # -----------------------------------------------------------------

    # TNL-CITA-LOCAL-LOCK-SLOT-V1
    if hay_bloqueo_local_cita(
        empresa=empresa,
        inicio=inicio,
        fin=fin,
    ):
        return {
            "disponible": False,
            "motivo": "ocupado_local",
            "ocupados": [],
            "calendar_id":
                google.calendar_id,
            "zona_horaria":
                google.zona_horaria,
            "reglas_agenda": True,
        }


    google_resultado = (
        consultar_disponibilidad(
            empresa=empresa,
            inicio=inicio,
            fin=fin,
        )
    )


    google_disponible = bool(
        google_resultado[
            "disponible"
        ]
    )


    return {
        "disponible":
            google_disponible,

        "motivo":
            (
                "disponible"
                if google_disponible
                else
                "ocupado_google"
            ),

        "ocupados":
            (
                google_resultado.get(
                    "ocupados"
                )
                or []
            ),

        "calendar_id":
            google_resultado[
                "calendar_id"
            ],

        "zona_horaria":
            google_resultado[
                "zona_horaria"
            ],

        "reglas_agenda":
            True,
    }
