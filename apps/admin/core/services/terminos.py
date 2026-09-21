"""
TNL-TERMINOS-SERVICE-V1

Autoridad central de Términos y Condiciones de NegocioListo.

Regla comercial vigente:

- Los términos aparecen únicamente antes de la PRIMERA
  vinculación realizada por el cliente/dueño.
- Una vez aceptados por la empresa, no se vuelven a exigir
  para WhatsApp, Google Calendar, Mercado Pago o reconexiones.
- La aceptación siempre se valida en servidor.
- JavaScript/SweetAlert es sólo interfaz, nunca autoridad.
"""

import hashlib
import ipaddress

from core.models import (
    AceptacionTerminos,
    PerfilUsuario,
)


TERMINOS_VERSION = (
    "AGOSTO-2026"
)

TERMINOS_TITULO = (
    "TÉRMINOS Y CONDICIONES GENERALES DE "
    "USO Y CONTRATACIÓN DEL SERVICIO "
    "“NEGOCIO LISTO”"
)


TERMINOS_CONTENIDO = """
TÉRMINOS Y CONDICIONES GENERALES DE
USO Y CONTRATACIÓN DEL SERVICIO
“NEGOCIO LISTO”

Última actualización: Agosto 2026

El presente documento constituye un contrato legalmente vinculante entre NEGOCIO LISTO / NEXOS ESTRATÉGICOS (en adelante, el “PRESTADOR”) y la persona física o moral que acepta estos términos mediante la casilla de verificación electrónica dispuesta dentro del panel del CLIENTE (en adelante, el “CLIENTE”). Al marcar la casilla “He leído y acepto los Términos y Condiciones del Servicio” y hacer clic en la acción de aceptación correspondiente, el CLIENTE manifiesta su consentimiento expreso a las siguientes cláusulas. El simple acceso al panel, la generación o escaneo de un código QR, el inicio de una autorización OAuth o la realización de un pago no sustituye por sí solo esta aceptación expresa.

CLÁUSULA PRIMERA. DEFINICIÓN Y ALCANCE DEL SERVICIO

El PRESTADOR suministra una plataforma de software como servicio (SaaS) y automatización conversacional multimodal dentro del entorno de WhatsApp, que incluye:

1. Conexión de interfaz y lógica conversacional para interacción con usuarios finales.
2. Módulo de catálogo digital, administración de productos y recepción de pedidos.
3. Integración con herramientas de calendario para agendamiento de citas y/o programación de entregas.

CLÁUSULA SEGUNDA. TARIFAS, CONDICIONES DE PAGO Y FACTURACIÓN

1. Cuota de Contratación / Setup Inicial: Se establece una tarifa única de implementación y configuración inicial por la cantidad de $2,999.00 MXN (Dos mil novecientos noventa y nueve pesos 00/100 M.N.).

2. Cuota de Mantenimiento y Suscripción Mensual: El CLIENTE pagará una cuota recurrente fija de $999.00 MXN (Novecientos noventa y nueve pesos 00/100 M.N.) cada 30 (treinta) días naturales a partir de la fecha de activación del servicio.

3. Régimen Fiscal / Impuesto al Valor Agregado (IVA): Todos los precios y tarifas estipuladas en este contrato corresponden al valor base del servicio. En caso de que el CLIENTE requiera Comprobante Fiscal Digital por Internet (CFDI/Factura), se agregará el 16% de Impuesto al Valor Agregado (IVA) tanto al importe de Contratación/Setup como a cada una de las mensualidades y recargas adicionales.

4. Política de Pagos Anuales: En contrataciones por esquema anual anticipado, el CLIENTE acepta expresamente que no habrá lugar a reembolsos totales ni proporcionales en caso de cancelación anticipada o desvinculación voluntaria antes del término de la anualidad.

CLÁUSULA TERCERA. POLÍTICA ESTRICTA DE ANTICIPOS Y NO REEMBOLSO

El CLIENTE reconoce y acepta que, al cubrir el anticipo o el pago total de contratación ($2,999.00 MXN), el PRESTADOR inicia de forma inmediata el aprovisionamiento de infraestructura de servidores, asignación de instancias de WhatsApp, reservación de bases de datos y horas técnicas de configuración en Mesa de Control. En consecuencia:

• Ningún anticipo o pago de contratación es reembolsable bajo ninguna circunstancia, ya que los recursos técnicos y operativos se devengan desde el momento en que se procesa el alta.

CLÁUSULA CUARTA. LÍMITES DE CONSUMO DE IA, AUDIOS DE VOZ Y PAQUETES DE RECARGA

El servicio mensual de $999.00 MXN incluye una bolsa base de consumo por ciclo mensual:

1. Bolsa Base de IA y Texto: Hasta 1,000 (mil) palabras/consultas procesadas por IA.

2. Bolsa Base de Voz (Audio): Hasta 150 (ciento cincuenta) respuestas sintetizadas por voz. La generación de voz está sujeta a la disponibilidad técnica de la red y APIs internacionales de síntesis de voz.

3. Consumo Agotado y Paquete Adicional:

• Una vez agotada la bolsa mensual de 1,000 palabras de IA o los 150 audios, el sistema suspenderá la generación automática de respuestas complejas de IA/voz y mantendrá operativo el menú interactivo de botones y texto base sin costo adicional.

• Si el CLIENTE desea reactivar la atención de IA y voz antes de su fecha de corte, podrá solicitar la activación de una Bolsa de Recarga Adicional por un costo de $150.00 MXN (+ IVA en caso de factura) por evento.

CLÁUSULA QUINTA. ALCANCE DE MESA DE CONTROL Y MODIFICACIONES INCLUIDAS

1. Horario de Atención: La Mesa de Control y Soporte Técnico operará de Lunes a Viernes en un horario de 10:00 AM a 7:00 PM (Hora del Centro de México). Las solicitudes recibidas fuera de este horario serán atendidas al siguiente día hábil.

2. Modificaciones Mensuales Incluidas: La suscripción mensual de $999.00 MXN ampara hasta 3 (tres) ajustes o modificaciones menores al mes dentro del flujo de su bot (tales como cambios de precios en catálogo, sustitución de textos o actualización de datos de contacto).

3. Ajustes Adicionales: A partir de la 4.ª (cuarta) solicitud de modificación en un mismo ciclo mensual, cada cambio adicional tendrá un costo de $250.00 MXN (+ IVA en caso de factura), el cual deberá liquidarse previo a la ejecución del cambio por la Mesa de Control.

CLÁUSULA SEXTA. CONDICIÓN PREVIA OBLIGATORIA (ONBOARDING)

Para iniciar la primera vinculación de servicios externos dentro de NegocioListo, el CLIENTE deberá aceptar previamente y de forma expresa estos Términos y Condiciones mediante la casilla de verificación disponible en su panel.

1. Mientras no exista una aceptación registrada, el CLIENTE no podrá iniciar desde su panel la vinculación de su línea de WhatsApp, su cuenta de Google para Google Calendar ni su cuenta de la pasarela de pagos habilitada por el PRESTADOR.

2. Una vez registrada la aceptación, el CLIENTE podrá completar las vinculaciones disponibles para su empresa, incluyendo el escaneo del código QR de WhatsApp y las autorizaciones OAuth correspondientes.

3. La aceptación inicial registrada será válida para las vinculaciones y reconexiones posteriores de la misma empresa mientras se mantenga vigente la versión de Términos y Condiciones aceptada, sin necesidad de presentar nuevamente la casilla en cada integración.

CLÁUSULA SÉPTIMA. PASARELAS DE PAGO Y TRANSACCIONES FINANCIERAS

1. El PRESTADOR únicamente facilita el enlace y configuración técnica entre la plataforma y el proveedor de pasarela de pagos digitales seleccionado (ej. Mercado Pago u otros procesadores autorizados).

2. Deslinde Financiero: El PRESTADOR no recibe, no custodia, no dispersa ni administra el dinero proveniente de las ventas o cobros del CLIENTE. Cualquier retención, contracargo, comisión por transacción bancaria, bloqueo de fondos o fallo técnico imputable a la pasarela de pagos es responsabilidad exclusiva del proveedor financiero y del CLIENTE, deslindando íntegramente al PRESTADOR de cualquier reclamación económica o legal al respecto.

CLÁUSULA OCTAVA. DESLINDE DE RESPONSABILIDAD POR FALLAS DE TERCEROS (APIs Y REDES)

1. El servicio depende de infraestructuras tecnológicas suministradas por terceros ajenos al PRESTADOR (incluyendo, de manera enunciativa más no limitativa: Meta/WhatsApp, proveedores de modelos de lenguaje OpenAI/Groq, plataformas de síntesis de voz, servidores en la nube y redes de telecomunicaciones).

2. El PRESTADOR no será responsable por suspensiones temporales del servicio, retrasos en la entrega de mensajes, caídas globales de servidores de WhatsApp o degradación en las respuestas de los modelos de inteligencia artificial derivados de fallas de dichos proveedores externos o interrupciones en la red de internet del CLIENTE o sus usuarios finales.

3. El CLIENTE es el único responsable del uso adecuado de su línea de WhatsApp y del cumplimiento de las políticas de uso y comercio de Meta.

CLÁUSULA NOVENA. PROPIEDAD INTELECTUAL Y LICENCIA DE USO

Todos los derechos de propiedad intelectual sobre el código fuente, la arquitectura de flujos, el software, las marcas y las plantillas maestras son propiedad exclusiva del PRESTADOR. Se otorga al CLIENTE una licencia de uso temporal, intransferible y no exclusiva mientras mantenga vigente y al corriente su cuota de suscripción mensual.

CLÁUSULA DÉCIMA. JURISDICCIÓN Y LEGISLACIÓN APLICABLE

Para la interpretación, cumplimiento y solución de cualquier controversia derivada del presente contrato, las partes se someten expresamente a las leyes aplicables de los Estados Unidos Mexicanos y a la jurisdicción de los tribunales competentes de la ciudad de Guadalajara, Jalisco, renunciando a cualquier otro fuero que pudiera corresponderles por razón de sus domicilios presentes o futuros.

DECLARACIÓN DE CONFORMIDAD:

Al marcar la casilla "He leído y acepto los Términos y Condiciones del Servicio" y confirmar electrónicamente su aceptación antes de la primera vinculación, el CLIENTE declara bajo protesta de decir verdad que tiene la capacidad legal para obligarse y que acepta la totalidad de las cláusulas aquí estipuladas.
""".strip()


TERMINOS_SHA256 = hashlib.sha256(
    TERMINOS_CONTENIDO.encode(
        "utf-8"
    )
).hexdigest()


class TerminosNoAceptadosError(
    Exception
):
    """
    La empresa aún no tiene aceptación registrada.
    """


class TerminosConfiguracionError(
    Exception
):
    """
    Inconsistencia interna del documento de términos.
    """


def obtener_aceptacion_empresa(
    empresa,
):
    """
    La regla vigente es UNA aceptación inicial
    por empresa.

    Si existe cualquier aceptación previa,
    las siguientes vinculaciones/reconexiones
    no vuelven a solicitar términos.
    """

    return (
        AceptacionTerminos.objects
        .filter(
            empresa=empresa
        )
        .select_related(
            "perfil_usuario",
            "perfil_usuario__usuario",
        )
        .order_by(
            "aceptado_en",
            "id",
        )
        .first()
    )


def terminos_aceptados(
    empresa,
):
    return (
        obtener_aceptacion_empresa(
            empresa
        )
        is not None
    )


def requerir_terminos_aceptados(
    empresa,
):

    aceptacion = (
        obtener_aceptacion_empresa(
            empresa
        )
    )

    if aceptacion is None:
        raise TerminosNoAceptadosError(
            "Debe aceptar los Términos y Condiciones."
        )

    return aceptacion


def _extraer_ip(
    request,
):

    candidatos = []

    x_forwarded_for = str(
        request.META.get(
            "HTTP_X_FORWARDED_FOR",
            "",
        )
        or
        ""
    ).strip()

    if x_forwarded_for:

        candidatos.extend(
            parte.strip()
            for parte
            in x_forwarded_for.split(",")
            if parte.strip()
        )


    remote_addr = str(
        request.META.get(
            "REMOTE_ADDR",
            "",
        )
        or
        ""
    ).strip()

    if remote_addr:
        candidatos.append(
            remote_addr
        )


    for candidato in candidatos:

        try:

            return str(
                ipaddress.ip_address(
                    candidato
                )
            )

        except ValueError:
            continue


    return None


def registrar_aceptacion(
    *,
    empresa,
    perfil,
    request,
    origen,
):
    """
    Registra la primera aceptación.

    Es idempotente:
    si la empresa ya aceptó anteriormente,
    devuelve la aceptación existente y NO
    genera una nueva fila.
    """

    if perfil is None:
        raise ValueError(
            "Perfil de cliente requerido."
        )

    if not perfil.activo:
        raise ValueError(
            "El perfil se encuentra inactivo."
        )

    if (
        perfil.rol
        != PerfilUsuario.Rol.CLIENTE
    ):
        raise ValueError(
            "Sólo el cliente principal puede aceptar."
        )

    if (
        perfil.empresa_id
        != empresa.pk
    ):
        raise ValueError(
            "El perfil no pertenece a la empresa."
        )


    origen = str(
        origen or ""
    ).strip()


    origenes_validos = {
        value
        for value, _label
        in AceptacionTerminos
        .OrigenVinculacion
        .choices
    }


    if origen not in origenes_validos:
        raise ValueError(
            "Origen de vinculación inválido."
        )


    existente = (
        obtener_aceptacion_empresa(
            empresa
        )
    )


    if existente is not None:

        return (
            existente,
            False,
        )


    usuario = perfil.usuario


    aceptacion, creada = (
        AceptacionTerminos.objects
        .get_or_create(
            empresa=empresa,
            version=
                TERMINOS_VERSION,

            defaults={
                "perfil_usuario":
                    perfil,

                "documento_sha256":
                    TERMINOS_SHA256,

                "contenido_snapshot":
                    TERMINOS_CONTENIDO,

                "origen_vinculacion":
                    origen,

                "usuario_username_snapshot":
                    str(
                        usuario.get_username()
                        or
                        ""
                    )[:150],

                "usuario_email_snapshot":
                    str(
                        getattr(
                            usuario,
                            "email",
                            "",
                        )
                        or
                        ""
                    )[:254],

                "ip_aceptacion":
                    _extraer_ip(
                        request
                    ),

                "user_agent":
                    str(
                        request.META.get(
                            "HTTP_USER_AGENT",
                            "",
                        )
                        or
                        ""
                    )[:2000],
            },
        )
    )


    if (
        aceptacion.documento_sha256
        != TERMINOS_SHA256
    ):
        raise TerminosConfiguracionError(
            "La versión registrada no coincide "
            "con el contenido canónico."
        )


    return (
        aceptacion,
        creada,
    )
