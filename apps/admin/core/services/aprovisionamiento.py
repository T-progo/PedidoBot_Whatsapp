from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from urllib.parse import urlencode
from uuid import UUID


# TNL-TYPEBOT-BEARER-PARAM-V1
_TYPEBOT_API_KEY_FILE = (
    "/opt/tunegociolisto/infrastructure/"
    "secrets/typebot_catalog_api_key"
)

_TYPEBOT_API_KEY_PLACEHOLDER = (
    "__TYPEBOT_API_KEY__"
)


from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.integrations.typebot_client import (
    TypebotClient,
    TypebotError,
)

from core.models import (
    Empresa,
    Licencia,
    Bot,
    Canal,
    Catalogo,
    Plantilla,
    Variable,
    PlantillaMaestra,
    InstalacionPlantilla,
)


def _texto_error(exc):
    """
    Convierte una excepción en texto seguro para auditoría.
    """

    if isinstance(exc, ValidationError):
        mensajes = getattr(exc, "messages", None)

        if mensajes:
            return " ".join(
                str(mensaje)
                for mensaje in mensajes
            )[:4000]

    return str(exc)[:4000]


def _nombre_limitado(modelo, campo, valor):
    """
    Respeta automáticamente el max_length del modelo destino.
    """

    field = modelo._meta.get_field(campo)
    max_length = getattr(field, "max_length", None)

    valor = str(valor).strip()

    if max_length:
        return valor[:max_length]

    return valor


def _validar_empresa(empresa):
    """
    Impide aprovisionar una empresa deshabilitada.
    """

    estado = getattr(
        empresa,
        "estado",
        None,
    )

    if estado is None:
        return

    estado_normalizado = str(
        estado
    ).strip().lower()

    if estado_normalizado not in {
        "activa",
        "activo",
    }:
        raise ValidationError(
            (
                f"La empresa {empresa} no está activa. "
                f"Estado actual: {estado}."
            )
        )


def _validar_licencia(
    licencia,
    empresa,
):
    """
    Valida propiedad, estado y vigencia de la licencia.
    """

    if licencia.empresa_id != empresa.id:
        raise ValidationError(
            "La licencia no pertenece a la empresa indicada."
        )

    if licencia.estado != "activa":
        raise ValidationError(
            (
                f"La licencia {licencia.nombre} "
                f"no está activa. "
                f"Estado actual: {licencia.estado}."
            )
        )

    hoy = timezone.localdate()

    if licencia.fecha_inicio > hoy:
        raise ValidationError(
            (
                f"La licencia {licencia.nombre} "
                "todavía no inicia. "
                f"Fecha de inicio: {licencia.fecha_inicio}."
            )
        )

    if licencia.fecha_fin < hoy:
        raise ValidationError(
            (
                f"La licencia {licencia.nombre} "
                "está vencida. "
                f"Fecha de fin: {licencia.fecha_fin}."
            )
        )


def _validar_plantilla_maestra(
    plantilla_maestra,
):
    """
    Solo permite instalar plantillas publicadas y activas.
    """

    if not plantilla_maestra.activa:
        raise ValidationError(
            (
                f"La plantilla maestra "
                f"{plantilla_maestra} está inactiva."
            )
        )

    if (
        plantilla_maestra.estado
        != PlantillaMaestra.Estado.PUBLICADA
    ):
        raise ValidationError(
            (
                f"La plantilla maestra "
                f"{plantilla_maestra} "
                "no está publicada."
            )
        )


def _moneda_catalogo(
    configuracion,
):
    """
    Obtiene una moneda válida para Catalogo.
    """

    moneda = str(
        configuracion.get(
            "moneda",
            "MXN",
        )
    ).upper()

    field = Catalogo._meta.get_field(
        "moneda"
    )

    monedas_validas = {
        str(valor)
        for valor, _etiqueta in field.choices
    }

    if moneda in monedas_validas:
        return moneda

    if "MXN" in monedas_validas:
        return "MXN"

    if monedas_validas:
        return sorted(
            monedas_validas
        )[0]

    return moneda



# ============================================================
# APROVISIONAMIENTO CANAL WHATSAPP V1
# ============================================================


def _asegurar_canal_whatsapp(
    bot,
):
    """
    Garantiza un único Canal WhatsApp por Bot.

    IMPORTANTE:
    - los canales existentes NO se modifican;
    - los nuevos nacen inactivos;
    - Evolution todavía no se conecta;
    - la restricción uniq_canal_bot_tipo protege concurrencia.
    """

    if bot is None:
        return None, False

    canal, creado = Canal.objects.get_or_create(
        bot=bot,
        tipo=Canal.Tipo.WHATSAPP,
        defaults={
            "nombre": "WhatsApp",
            "identificador": "",
            "activo": False,
        },
    )

    return canal, creado



# ============================================================
# APROVISIONAMIENTO TYPEBOT V2
# ============================================================


def _configuracion_maestra(
    plantilla_maestra,
):
    """
    Devuelve una configuración segura para la plantilla maestra.
    """

    if isinstance(
        plantilla_maestra.configuracion,
        dict,
    ):
        return plantilla_maestra.configuracion

    return {}


def _requiere_typebot(
    plantilla_maestra,
):
    """
    Solo aprovisiona Typebot cuando:
    - la plantilla crea Bot;
    - la maestra tiene Typebot origen asociado.

    Esto mantiene compatibilidad con maestras históricas que
    todavía no tienen identificador_externo.
    """

    configuracion = _configuracion_maestra(
        plantilla_maestra
    )

    crear_bot = configuracion.get(
        "crear_bot",
        True,
    )

    origen_id = str(
        getattr(
            plantilla_maestra,
            "identificador_externo",
            "",
        )
        or ""
    ).strip()

    return bool(
        crear_bot
        and origen_id
    )


def _extraer_typebot(
    respuesta,
):
    """
    Normaliza respuestas de la API de Typebot.
    """

    if not isinstance(
        respuesta,
        dict,
    ):
        raise TypebotError(
            "La respuesta de Typebot no es válida."
        )

    data = respuesta.get(
        "data",
        {},
    )

    if not isinstance(
        data,
        dict,
    ):
        raise TypebotError(
            "Typebot devolvió data inválida."
        )

    typebot = data.get(
        "typebot",
        data,
    )

    if not isinstance(
        typebot,
        dict,
    ):
        raise TypebotError(
            "Typebot no devolvió un objeto typebot válido."
        )

    return typebot


def _nombre_typebot_instalacion(
    *,
    instalacion,
    empresa,
    plantilla_maestra,
):
    """
    Nombre determinista.

    TNL-I<ID> permite recuperar un clon creado antes de una
    interrupción sin generar otro duplicado.
    """

    nombre = (
        f"{empresa.nombre} - "
        f"{plantilla_maestra.nombre} "
        f"v{plantilla_maestra.version} "
        f"- TNL-I{instalacion.id}"
    )

    return nombre[:150]



# TNL-PRODUCT-IMAGE-INVARIANTS-V1
def _validar_invariantes_imagenes_producto_typebot(
    typebot,
    *,
    contexto,
):
    """
    Valida el contrato de imágenes para Typebots que utilizan
    las tarjetas de productos de NegocioListo.

    No depende de Empresa, Bot ni PlantillaMaestra concreta.

    El guard se activa únicamente cuando el Typebot contiene
    el patrón funcional de tarjetas de producto:
    - internalValue={{producto_ids}}
    - description={{producto_tarjeta_descripciones}}

    Si aplica, exige:
    - una única variable producto_imagenes_principales;
    - imageUrl={{producto_imagenes_principales}} en cada
      tarjeta de producto;
    - un mapping data.imagenes_principales hacia esa variable
      en cada respuesta HTTP que mapea
      data.tarjeta_descripciones.
    """

    if not isinstance(
        typebot,
        dict,
    ):
        raise TypebotError(
            (
                "SEGURIDAD: "
                f"{contexto} no contiene "
                "un Typebot válido para validar imágenes."
            )
        )

    groups = (
        typebot.get("groups")
        or []
    )

    variables = (
        typebot.get("variables")
        or []
    )

    variables_imagen = [
        variable
        for variable
        in variables
        if (
            isinstance(
                variable,
                dict,
            )
            and
            str(
                variable.get("name")
                or ""
            ).strip()
            ==
            "producto_imagenes_principales"
        )
    ]

    tarjetas_producto = []
    bloques_http_producto = []

    for grupo in groups:

        if not isinstance(
            grupo,
            dict,
        ):
            continue

        for bloque in (
            grupo.get("blocks")
            or []
        ):

            if not isinstance(
                bloque,
                dict,
            ):
                continue

            # ------------------------------------------------
            # TARJETAS DE PRODUCTO
            # ------------------------------------------------

            if (
                bloque.get("type")
                ==
                "cards"
            ):

                for item in (
                    bloque.get("items")
                    or []
                ):

                    if not isinstance(
                        item,
                        dict,
                    ):
                        continue

                    options = (
                        item.get("options")
                        or {}
                    )

                    if (
                        str(
                            options.get(
                                "internalValue"
                            )
                            or ""
                        ).strip()
                        ==
                        "{{producto_ids}}"
                        and
                        str(
                            item.get(
                                "description"
                            )
                            or ""
                        ).strip()
                        ==
                        "{{producto_tarjeta_descripciones}}"
                    ):

                        tarjetas_producto.append(
                            (
                                grupo,
                                bloque,
                                item,
                            )
                        )

            # ------------------------------------------------
            # RESPONSE VARIABLE MAPPINGS
            # ------------------------------------------------

            options = (
                bloque.get("options")
                or {}
            )

            mappings = (
                options.get(
                    "responseVariableMapping"
                )
                or []
            )

            if not isinstance(
                mappings,
                list,
            ):
                continue

            tiene_descripciones = any(
                (
                    isinstance(
                        mapping,
                        dict,
                    )
                    and
                    str(
                        mapping.get(
                            "bodyPath"
                        )
                        or ""
                    ).strip()
                    ==
                    "data.tarjeta_descripciones"
                )
                for mapping
                in mappings
            )

            if tiene_descripciones:

                bloques_http_producto.append(
                    (
                        grupo,
                        bloque,
                        mappings,
                    )
                )

    aplica = bool(
        tarjetas_producto
        or bloques_http_producto
    )

    if not aplica:

        return {
            "aplica": False,
            "variables_imagen": 0,
            "tarjetas_producto": 0,
            "mappings_imagen": 0,
        }

    if not tarjetas_producto:

        raise TypebotError(
            (
                "SEGURIDAD: "
                f"{contexto} contiene flujo HTTP "
                "de productos pero no contiene "
                "tarjetas de producto compatibles."
            )
        )

    if not bloques_http_producto:

        raise TypebotError(
            (
                "SEGURIDAD: "
                f"{contexto} contiene tarjetas "
                "de productos pero no contiene "
                "mappings HTTP compatibles."
            )
        )

    if len(
        variables_imagen
    ) != 1:

        raise TypebotError(
            (
                "SEGURIDAD: "
                f"{contexto} debe contener "
                "exactamente una variable "
                "producto_imagenes_principales; "
                f"encontradas={len(variables_imagen)}."
            )
        )

    variable_imagen = (
        variables_imagen[0]
    )

    variable_imagen_id = str(
        variable_imagen.get("id")
        or ""
    ).strip()

    if not variable_imagen_id:

        raise TypebotError(
            (
                "SEGURIDAD: "
                f"{contexto} contiene la variable "
                "producto_imagenes_principales "
                "sin ID."
            )
        )

    for (
        grupo,
        bloque,
        item,
    ) in tarjetas_producto:

        image_url = str(
            item.get("imageUrl")
            or ""
        ).strip()

        if (
            image_url
            !=
            "{{producto_imagenes_principales}}"
        ):

            raise TypebotError(
                (
                    "SEGURIDAD: "
                    f"{contexto} contiene una "
                    "tarjeta de producto sin el "
                    "imageUrl obligatorio. "
                    f"group_id={grupo.get('id')} "
                    f"block_id={bloque.get('id')} "
                    f"item_id={item.get('id')}."
                )
            )

    mappings_imagen_total = 0

    for (
        grupo,
        bloque,
        mappings,
    ) in bloques_http_producto:

        mappings_imagen = [
            mapping
            for mapping
            in mappings
            if (
                isinstance(
                    mapping,
                    dict,
                )
                and
                str(
                    mapping.get(
                        "bodyPath"
                    )
                    or ""
                ).strip()
                ==
                "data.imagenes_principales"
            )
        ]

        if len(
            mappings_imagen
        ) != 1:

            raise TypebotError(
                (
                    "SEGURIDAD: "
                    f"{contexto} debe contener "
                    "exactamente un mapping "
                    "data.imagenes_principales "
                    "por búsqueda de productos. "
                    f"group_id={grupo.get('id')} "
                    f"block_id={bloque.get('id')} "
                    f"encontrados={len(mappings_imagen)}."
                )
            )

        mapping = (
            mappings_imagen[0]
        )

        if (
            str(
                mapping.get(
                    "variableId"
                )
                or ""
            ).strip()
            !=
            variable_imagen_id
        ):

            raise TypebotError(
                (
                    "SEGURIDAD: "
                    f"{contexto} contiene un mapping "
                    "data.imagenes_principales "
                    "asociado a una variable incorrecta. "
                    f"group_id={grupo.get('id')} "
                    f"block_id={bloque.get('id')}."
                )
            )

        mappings_imagen_total += 1

    return {
        "aplica": True,
        "variables_imagen":
            len(
                variables_imagen
            ),
        "tarjetas_producto":
            len(
                tarjetas_producto
            ),
        "mappings_imagen":
            mappings_imagen_total,
    }



# TNL-TYPEBOT-CONVERSATION-IDENTITY-V1
_TYPEBOT_TECHNICAL_SESSION_VARIABLES = (
    "remoteJid",
    "instanceName",
)

_TYPEBOT_IA_WEBHOOK_PATH = (
    "/api/typebot/ia/responder/"
)


def _typebot_technical_variable_id(
    name,
):
    """
    Genera un ID técnico estable sin incorporar
    empresa, teléfono, JID ni datos del usuario.
    """

    if (
        name
        not in
        _TYPEBOT_TECHNICAL_SESSION_VARIABLES
    ):
        raise TypebotError(
            (
                "Variable técnica Typebot "
                f"no permitida: {name!r}."
            )
        )

    seed = (
        "negociolisto:typebot:"
        "technical-session-variable:"
        f"{name}"
    )

    return hashlib.sha256(
        seed.encode(
            "utf-8"
        )
    ).hexdigest()[:24]


def _variables_typebot_indexadas(
    variables,
    *,
    contexto,
):
    """
    Indexa variables Typebot y rechaza IDs duplicados.
    """

    if not isinstance(
        variables,
        list,
    ):
        raise TypebotError(
            (
                f"{contexto}: "
                "variables no es una lista."
            )
        )

    por_id = {}
    por_nombre = {}

    for variable in variables:

        if not isinstance(
            variable,
            dict,
        ):
            raise TypebotError(
                (
                    f"{contexto}: "
                    "existe una variable inválida."
                )
            )

        variable_id = str(
            variable.get("id")
            or ""
        ).strip()

        nombre = str(
            variable.get("name")
            or ""
        ).strip()

        if not variable_id:
            raise TypebotError(
                (
                    f"{contexto}: "
                    "existe una variable sin ID."
                )
            )

        if variable_id in por_id:
            raise TypebotError(
                (
                    f"{contexto}: "
                    "ID de variable duplicado."
                )
            )

        por_id[
            variable_id
        ] = variable

        if nombre:

            por_nombre.setdefault(
                nombre,
                [],
            ).append(
                variable
            )

    return (
        por_id,
        por_nombre,
    )


def _validar_variables_tecnicas_clon_typebot(
    origen,
    clon,
):
    """
    Conserva todas las variables del origen y permite
    únicamente las dos variables técnicas de sesión.

    Permite estado parcial 0/1/2 para recuperación
    idempotente, pero nunca variables extra ajenas.
    """

    variables_origen = (
        origen.get(
            "variables"
        )
        or []
    )

    variables_clon = (
        clon.get(
            "variables"
        )
        or []
    )

    (
        origen_por_id,
        _,
    ) = _variables_typebot_indexadas(
        variables_origen,
        contexto=(
            "Typebot origen"
        ),
    )

    (
        clon_por_id,
        clon_por_nombre,
    ) = _variables_typebot_indexadas(
        variables_clon,
        contexto=(
            "clon Typebot"
        ),
    )

    #
    # Todas las variables originales deben continuar.
    #
    for (
        variable_id,
        variable_origen,
    ) in origen_por_id.items():

        variable_clon = (
            clon_por_id.get(
                variable_id
            )
        )

        if variable_clon is None:
            raise TypebotError(
                (
                    "El clon Typebot perdió "
                    "una variable del maestro."
                )
            )

        if (
            str(
                variable_clon.get(
                    "name"
                )
                or ""
            )
            !=
            str(
                variable_origen.get(
                    "name"
                )
                or ""
            )
        ):
            raise TypebotError(
                (
                    "El clon Typebot modificó "
                    "el nombre de una variable "
                    "del maestro."
                )
            )

        if (
            variable_clon.get(
                "isSessionVariable"
            )
            !=
            variable_origen.get(
                "isSessionVariable"
            )
        ):
            raise TypebotError(
                (
                    "El clon Typebot modificó "
                    "el tipo de sesión de una "
                    "variable del maestro."
                )
            )

    extras = [
        variable
        for variable_id, variable
        in clon_por_id.items()
        if variable_id
        not in origen_por_id
    ]

    permitidas = set(
        _TYPEBOT_TECHNICAL_SESSION_VARIABLES
    )

    nombres_extra = [
        str(
            variable.get(
                "name"
            )
            or ""
        ).strip()
        for variable in extras
    ]

    if any(
        nombre
        not in permitidas
        for nombre in nombres_extra
    ):
        raise TypebotError(
            (
                "El clon Typebot contiene "
                "variables extra no permitidas."
            )
        )

    if (
        len(
            nombres_extra
        )
        !=
        len(
            set(
                nombres_extra
            )
        )
    ):
        raise TypebotError(
            (
                "El clon Typebot contiene "
                "variables técnicas duplicadas."
            )
        )

    if len(
        extras
    ) > len(
        permitidas
    ):
        raise TypebotError(
            (
                "El clon Typebot contiene "
                "demasiadas variables técnicas."
            )
        )

    #
    # Si existe una técnica, debe cumplir
    # exactamente nuestro contrato.
    #
    for nombre in (
        _TYPEBOT_TECHNICAL_SESSION_VARIABLES
    ):

        coincidencias = (
            clon_por_nombre.get(
                nombre,
                [],
            )
        )

        if len(
            coincidencias
        ) > 1:
            raise TypebotError(
                (
                    "Variable técnica Typebot "
                    f"duplicada: {nombre}."
                )
            )

        if not coincidencias:
            continue

        variable = (
            coincidencias[0]
        )

        if (
            str(
                variable.get(
                    "id"
                )
                or ""
            )
            !=
            _typebot_technical_variable_id(
                nombre
            )
        ):
            raise TypebotError(
                (
                    "Variable técnica Typebot "
                    f"con ID inesperado: {nombre}."
                )
            )

        if (
            variable.get(
                "isSessionVariable"
            )
            is not True
        ):
            raise TypebotError(
                (
                    "Variable técnica Typebot "
                    "no marcada como sesión: "
                    f"{nombre}."
                )
            )

    return {
        "origen":
            len(
                variables_origen
            ),

        "clon":
            len(
                variables_clon
            ),

        "extras":
            sorted(
                nombres_extra
            ),
    }


def _preparar_variables_tecnicas_typebot(
    typebot,
):
    """
    Agrega idempotentemente las variables técnicas
    necesarias para prefilledVariables de Evolution.
    """

    variables = deepcopy(
        typebot.get(
            "variables"
        )
        or []
    )

    (
        por_id,
        por_nombre,
    ) = _variables_typebot_indexadas(
        variables,
        contexto=(
            "Typebot a parametrizar"
        ),
    )

    agregadas = []

    for nombre in (
        _TYPEBOT_TECHNICAL_SESSION_VARIABLES
    ):

        coincidencias = (
            por_nombre.get(
                nombre,
                [],
            )
        )

        if len(
            coincidencias
        ) > 1:
            raise TypebotError(
                (
                    "Variable técnica Typebot "
                    f"duplicada: {nombre}."
                )
            )

        variable_id = (
            _typebot_technical_variable_id(
                nombre
            )
        )

        if coincidencias:

            variable = (
                coincidencias[0]
            )

            if (
                str(
                    variable.get(
                        "id"
                    )
                    or ""
                )
                != variable_id
            ):
                raise TypebotError(
                    (
                        "Variable técnica Typebot "
                        "existente con ID inesperado: "
                        f"{nombre}."
                    )
                )

            if (
                variable.get(
                    "isSessionVariable"
                )
                is not True
            ):
                raise TypebotError(
                    (
                        "Variable técnica Typebot "
                        "existente no es de sesión: "
                        f"{nombre}."
                    )
                )

            continue

        if variable_id in por_id:
            raise TypebotError(
                (
                    "Colisión de ID al crear "
                    "variable técnica Typebot."
                )
            )

        nueva = {
            "id":
                variable_id,

            "name":
                nombre,

            "isSessionVariable":
                True,
        }

        variables.append(
            nueva
        )

        por_id[
            variable_id
        ] = nueva

        por_nombre[
            nombre
        ] = [
            nueva
        ]

        agregadas.append(
            nombre
        )

    return (
        variables,
        agregadas,
    )


def _parsear_body_webhook_ia_typebot(
    body,
):
    """
    Convierte el body IA en dict sin aceptar
    formatos ambiguos.
    """

    if isinstance(
        body,
        dict,
    ):
        return deepcopy(
            body
        )

    if isinstance(
        body,
        str,
    ):

        try:
            parsed = json.loads(
                body
            )
        except Exception as exc:
            raise TypebotError(
                (
                    "El body del webhook IA "
                    "no contiene JSON válido."
                )
            ) from exc

        if not isinstance(
            parsed,
            dict,
        ):
            raise TypebotError(
                (
                    "El body del webhook IA "
                    "no contiene un objeto JSON."
                )
            )

        return parsed

    raise TypebotError(
        (
            "El body del webhook IA "
            "tiene un formato inesperado."
        )
    )


def _preparar_identidad_ia_typebot(
    groups,
):
    """
    Incorpora exclusivamente las referencias técnicas
    necesarias en el webhook IA.

    Conserva el tipo original del body.
    """

    groups_nuevos = deepcopy(
        groups
    )

    referencias = 0
    cambios = 0

    for group in groups_nuevos:

        if not isinstance(
            group,
            dict,
        ):
            continue

        for block in (
            group.get(
                "blocks"
            )
            or []
        ):

            if not isinstance(
                block,
                dict,
            ):
                continue

            options = (
                block.get(
                    "options"
                )
                or {}
            )

            if not isinstance(
                options,
                dict,
            ):
                continue

            webhook = (
                options.get(
                    "webhook"
                )
            )

            if not isinstance(
                webhook,
                dict,
            ):
                continue

            url = str(
                webhook.get(
                    "url"
                )
                or ""
            )

            if (
                _TYPEBOT_IA_WEBHOOK_PATH
                not in url
            ):
                continue

            referencias += 1

            body_original = (
                webhook.get(
                    "body"
                )
            )

            body = (
                _parsear_body_webhook_ia_typebot(
                    body_original
                )
            )

            if "bot_id" not in body:
                raise TypebotError(
                    (
                        "El webhook IA no "
                        "contiene bot_id."
                    )
                )

            if "mensaje" not in body:
                raise TypebotError(
                    (
                        "El webhook IA no "
                        "contiene mensaje."
                    )
                )

            body_nuevo = deepcopy(
                body
            )

            body_nuevo[
                "remote_jid"
            ] = "{{remoteJid}}"

            body_nuevo[
                "instance_name"
            ] = "{{instanceName}}"

            if body_nuevo == body:
                continue

            if isinstance(
                body_original,
                str,
            ):

                webhook[
                    "body"
                ] = json.dumps(
                    body_nuevo,
                    ensure_ascii=False,
                    indent=2,
                )

            else:

                webhook[
                    "body"
                ] = body_nuevo

            cambios += 1

    if referencias != 1:
        raise TypebotError(
            (
                "Se esperaba exactamente "
                "un webhook IA por Typebot; "
                f"se encontraron {referencias}."
            )
        )

    return (
        groups_nuevos,
        referencias,
        cambios,
    )


def _validar_identidad_ia_typebot(
    typebot,
):
    """
    Certifica que las dos variables técnicas y el
    webhook IA ya están en su estado definitivo.
    """

    variables_actuales = (
        typebot.get(
            "variables"
        )
        or []
    )

    (
        variables_proyectadas,
        agregadas,
    ) = (
        _preparar_variables_tecnicas_typebot(
            typebot
        )
    )

    if (
        agregadas
        or
        variables_proyectadas
        != variables_actuales
    ):
        raise TypebotError(
            (
                "El Typebot no conserva "
                "las variables técnicas "
                "de identidad esperadas."
            )
        )

    groups_actuales = (
        typebot.get(
            "groups"
        )
        or []
    )

    (
        groups_proyectados,
        referencias,
        cambios,
    ) = (
        _preparar_identidad_ia_typebot(
            groups_actuales
        )
    )

    if (
        cambios
        or
        groups_proyectados
        != groups_actuales
    ):
        raise TypebotError(
            (
                "El webhook IA no conserva "
                "la identidad conversacional "
                "esperada."
            )
        )

    return referencias


def _validar_clon_typebot(
    *,
    origen,
    clon,
    nombre_esperado,
    permitir_publicado=False,
):
    """
    Comprueba que el clon sea independiente y completo.
    """

    _validar_invariantes_imagenes_producto_typebot(
        origen,
        contexto="Typebot maestro",
    )

    _validar_invariantes_imagenes_producto_typebot(
        clon,
        contexto="clon Typebot",
    )

    origen_id = str(
        origen.get("id")
        or ""
    ).strip()

    clon_id = str(
        clon.get("id")
        or ""
    ).strip()

    if not clon_id:
        raise TypebotError(
            "El clon Typebot no tiene ID."
        )

    if clon_id == origen_id:
        raise TypebotError(
            "SEGURIDAD: el clon tiene el mismo ID que el maestro."
        )

    if clon.get("name") != nombre_esperado:
        raise TypebotError(
            "El clon Typebot tiene un nombre inesperado."
        )

    if clon.get("isArchived") is True:
        raise TypebotError(
            "El clon Typebot está archivado."
        )

    if (
        clon.get("publicId")
        and not permitir_publicado
    ):
        raise TypebotError(
            "El clon Typebot fue creado publicado inesperadamente."
        )

    # TNL-TYPEBOT-CONVERSATION-IDENTITY-V1
    for campo in (
        "groups",
        "edges",
        "events",
    ):

        cantidad_origen = len(
            origen.get(campo)
            or []
        )

        cantidad_clon = len(
            clon.get(campo)
            or []
        )

        if cantidad_origen != cantidad_clon:
            raise TypebotError(
                (
                    f"El clon Typebot no conserva "
                    f"la estructura de {campo}: "
                    f"{cantidad_origen} != {cantidad_clon}."
                )
            )

    _validar_variables_tecnicas_clon_typebot(
        origen,
        clon,
    )

    return clon_id


def _buscar_typebot_por_nombre(
    *,
    client,
    workspace_id,
    nombre,
):
    """
    Busca un Typebot operativo por nombre exacto.

    Se utiliza para recuperar aprovisionamientos interrumpidos.
    """

    respuesta = client.listar_typebots(
        workspace_id=workspace_id,
    )

    if not respuesta["ok"]:
        raise TypebotError(
            (
                "Typebot no permitió listar bots "
                "durante la recuperación idempotente."
            )
        )

    typebots = (
        respuesta["data"]
        .get(
            "typebots",
            [],
        )
    )

    coincidencias = [
        typebot
        for typebot in typebots
        if (
            typebot.get("name")
            == nombre
            and not typebot.get(
                "isArchived",
                False,
            )
        )
    ]

    if len(coincidencias) > 1:
        raise TypebotError(
            (
                "Existen varios Typebots operativos "
                "con el nombre determinista de esta instalación. "
                "Debe revisarse manualmente."
            )
        )

    if not coincidencias:
        return None

    return str(
        coincidencias[0].get("id")
        or ""
    ).strip() or None


def _construir_public_id_typebot(
    *,
    instalacion,
):
    """
    Construye el publicId determinista
    para una instalación.
    """

    try:
        empresa_id = int(
            instalacion.empresa_id
        )

        instalacion_id = int(
            instalacion.id
        )

    except (
        TypeError,
        ValueError,
        AttributeError,
    ) as exc:

        raise TypebotError(
            (
                "No fue posible construir "
                "el publicId de la instalación."
            )
        ) from exc


    if (
        empresa_id <= 0
        or
        instalacion_id <= 0
    ):

        raise TypebotError(
            (
                "Empresa o instalación inválida "
                "para construir publicId."
            )
        )


    return (
        f"tnl-e{empresa_id}"
        f"-i{instalacion_id}"
    )


def _asegurar_public_id_typebot(
    *,
    client,
    typebot_id,
    plantilla_maestra,
    instalacion,
):
    """
    Garantiza el publicId del clon operativo.

    Nunca modifica la maestra.

    Si el clon ya posee un publicId válido,
    lo conserva para mantener compatibilidad
    con instalaciones creadas anteriormente.

    Solo genera el identificador determinista
    cuando el clon todavía no tiene publicId.
    """

    destino_id = str(
        typebot_id
        or ""
    ).strip()

    maestro_id = str(
        plantilla_maestra.identificador_externo
        or ""
    ).strip()


    if not destino_id:

        raise TypebotError(
            "No se recibió Typebot para asignar publicId."
        )


    if not maestro_id:

        raise TypebotError(
            "La Plantilla Maestra no tiene Typebot."
        )


    if destino_id == maestro_id:

        raise TypebotError(
            (
                "SEGURIDAD: nunca asignar publicId "
                "al Typebot maestro."
            )
        )


    public_id_esperado = (
        _construir_public_id_typebot(
            instalacion=instalacion,
        )
    )


    respuesta_antes = (
        client.obtener_typebot(
            destino_id
        )
    )


    if not respuesta_antes["ok"]:

        raise TypebotError(
            (
                "No fue posible comprobar el clon "
                "antes de asignar publicId. "
                f"HTTP {respuesta_antes['status']}."
            )
        )


    antes = _extraer_typebot(
        respuesta_antes
    )


    if (
        str(
            antes.get("id")
            or ""
        ).strip()
        != destino_id
    ):

        raise TypebotError(
            (
                "Typebot devolvió un clon diferente "
                "antes de asignar publicId."
            )
        )


    if antes.get(
        "isArchived"
    ) is True:

        raise TypebotError(
            (
                "No se puede asignar publicId "
                "a un clon archivado."
            )
        )


    public_id_actual = str(
        antes.get("publicId")
        or ""
    ).strip()


    if public_id_actual:

        return {
            "configurado": True,
            "actualizado": False,
            "public_id":
                public_id_actual,
        }


    respuesta_patch = (
        client.actualizar_typebot(
            destino_id,
            typebot={
                "publicId":
                    public_id_esperado,
            },
            overwrite=True,
        )
    )


    if not respuesta_patch["ok"]:

        raise TypebotError(
            (
                "Typebot rechazó la asignación "
                "del publicId. "
                f"HTTP {respuesta_patch['status']}."
            )
        )


    comprobacion = (
        client.obtener_typebot(
            destino_id
        )
    )


    if not comprobacion["ok"]:

        raise TypebotError(
            (
                "No fue posible verificar publicId "
                "después del PATCH. "
                f"HTTP {comprobacion['status']}."
            )
        )


    despues = _extraer_typebot(
        comprobacion
    )


    if (
        str(
            despues.get("id")
            or ""
        ).strip()
        != destino_id
    ):

        raise TypebotError(
            (
                "La verificación de publicId "
                "devolvió otro Typebot."
            )
        )


    if despues.get(
        "isArchived"
    ) is True:

        raise TypebotError(
            (
                "El clon quedó archivado "
                "después de asignar publicId."
            )
        )


    if (
        str(
            despues.get("publicId")
            or ""
        ).strip()
        != public_id_esperado
    ):

        raise TypebotError(
            (
                "Asignación no verificable: "
                "publicId inesperado."
            )
        )


    return {
        "configurado": True,
        "actualizado": True,
        "public_id":
            public_id_esperado,
    }


def _extraer_typebot_publicado(
    respuesta,
):
    """
    Extrae publishedTypebot de Typebot 3.17.x.
    """

    if not isinstance(
        respuesta,
        dict,
    ):
        return None


    data = respuesta.get(
        "data"
    )


    if not isinstance(
        data,
        dict,
    ):
        return None


    publicado = data.get(
        "publishedTypebot"
    )


    if not isinstance(
        publicado,
        dict,
    ):
        return None


    return publicado


def _publicar_typebot_si_necesario(
    *,
    client,
    typebot_id,
    plantilla_maestra,
    forzar_publicacion=False,
):
    """
    Garantiza el snapshot PublicTypebot.

    La fuente de verdad de publicación es
    GET /publishedTypebot.
    """

    destino_id = str(
        typebot_id
        or ""
    ).strip()

    maestro_id = str(
        plantilla_maestra.identificador_externo
        or ""
    ).strip()


    if not destino_id:

        raise TypebotError(
            "No se recibió Typebot para publicar."
        )


    if not maestro_id:

        raise TypebotError(
            "La Plantilla Maestra no tiene Typebot."
        )


    if destino_id == maestro_id:

        raise TypebotError(
            "SEGURIDAD: nunca publicar el Typebot maestro."
        )


    respuesta_editable = (
        client.obtener_typebot(
            destino_id
        )
    )


    if not respuesta_editable["ok"]:

        raise TypebotError(
            (
                "No fue posible comprobar el clon "
                "antes de publicar. "
                f"HTTP {respuesta_editable['status']}."
            )
        )


    editable = _extraer_typebot(
        respuesta_editable
    )


    if (
        str(
            editable.get("id")
            or ""
        ).strip()
        != destino_id
    ):

        raise TypebotError(
            "Typebot devolvió un clon diferente."
        )


    if editable.get(
        "isArchived"
    ) is True:

        raise TypebotError(
            "No se puede publicar un clon archivado."
        )


    respuesta_publicado_antes = (
        client.obtener_typebot_publicado(
            destino_id
        )
    )


    if not respuesta_publicado_antes["ok"]:

        raise TypebotError(
            (
                "No fue posible consultar "
                "publishedTypebot. "
                f"HTTP {respuesta_publicado_antes['status']}."
            )
        )


    publicado_antes = (
        _extraer_typebot_publicado(
            respuesta_publicado_antes
        )
    )


    ya_publicado = (
        publicado_antes
        is not None
    )


    if publicado_antes is not None:

        published_typebot_id = str(
            publicado_antes.get(
                "typebotId"
            )
            or ""
        ).strip()


        if (
            published_typebot_id
            and
            published_typebot_id
            != destino_id
        ):

            raise TypebotError(
                (
                    "publishedTypebot pertenece "
                    "a otro Typebot."
                )
            )


    if (
        ya_publicado
        and
        not forzar_publicacion
    ):

        return {
            "publicado": True,
            "ya_publicado": True,
            "publish_ejecutado": False,
        }


    respuesta_publicar = (
        client.publicar_typebot(
            destino_id
        )
    )


    if not respuesta_publicar["ok"]:

        raise TypebotError(
            (
                "Typebot rechazó la publicación. "
                f"HTTP {respuesta_publicar['status']}."
            )
        )


    comprobacion = (
        client.obtener_typebot_publicado(
            destino_id
        )
    )


    if not comprobacion["ok"]:

        raise TypebotError(
            (
                "Typebot respondió a publish, "
                "pero publishedTypebot no pudo "
                "consultarse después. "
                f"HTTP {comprobacion['status']}."
            )
        )


    publicado_despues = (
        _extraer_typebot_publicado(
            comprobacion
        )
    )


    if publicado_despues is None:

        raise TypebotError(
            (
                "Publicación no verificable: "
                "publishedTypebot continúa ausente."
            )
        )


    published_typebot_id = str(
        publicado_despues.get(
            "typebotId"
        )
        or ""
    ).strip()


    if (
        published_typebot_id
        and
        published_typebot_id
        != destino_id
    ):

        raise TypebotError(
            (
                "La publicación verificada pertenece "
                "a otro Typebot."
            )
        )


    return {
        "publicado": True,
        "ya_publicado": ya_publicado,
        "publish_ejecutado": True,
    }



def _archivar_typebot_rollback(
    *,
    client,
    typebot_id,
):
    """
    Rollback externo.

    Typebot 3.17.2 realiza eliminación lógica:
    DELETE correcto => isArchived=True.
    """

    respuesta = client.eliminar_typebot(
        typebot_id
    )

    if not respuesta["ok"]:
        return (
            "Rollback Typebot falló: "
            f"HTTP {respuesta['status']} "
            f"{respuesta['data']}"
        )[:1500]

    comprobacion = client.obtener_typebot(
        typebot_id
    )

    if not comprobacion["ok"]:

        if comprobacion["status"] == 404:
            return ""

        return (
            "Rollback Typebot no pudo comprobarse: "
            f"HTTP {comprobacion['status']}."
        )[:1500]

    typebot = _extraer_typebot(
        comprobacion
    )

    if typebot.get("isArchived") is not True:
        return (
            "Rollback Typebot respondió correctamente, "
            "pero el clon continúa operativo."
        )

    return ""


def _obtener_o_clonar_typebot(
    *,
    client,
    instalacion,
    empresa,
    plantilla_maestra,
):
    """
    Obtiene un clon previo de esta instalación o crea uno nuevo.

    El nombre determinista evita duplicados si el proceso se
    interrumpe después de crear Typebot y antes de persistir
    su ID en Django.
    """

    origen_id = str(
        plantilla_maestra.identificador_externo
        or ""
    ).strip()

    if not origen_id:
        return {
            "typebot_id": "",
            "creado": False,
            "recuperado": False,
            "nombre": "",
        }

    respuesta_origen = (
        client.obtener_typebot(
            origen_id
        )
    )

    if not respuesta_origen["ok"]:
        raise TypebotError(
            (
                "No fue posible obtener el Typebot maestro "
                f"{origen_id}. "
                f"HTTP {respuesta_origen['status']}."
            )
        )

    origen = _extraer_typebot(
        respuesta_origen
    )

    _validar_invariantes_imagenes_producto_typebot(
        origen,
        contexto="Typebot maestro antes de clonar",
    )

    if origen.get("isArchived") is True:
        raise TypebotError(
            "El Typebot maestro está archivado."
        )

    workspace = (
        client.resolver_workspace()
    )

    workspace_id = workspace.get(
        "id"
    )

    if not workspace_id:
        raise TypebotError(
            "Typebot no devolvió workspace_id."
        )

    nombre = (
        _nombre_typebot_instalacion(
            instalacion=instalacion,
            empresa=empresa,
            plantilla_maestra=(
                plantilla_maestra
            ),
        )
    )

    existente_id = (
        _buscar_typebot_por_nombre(
            client=client,
            workspace_id=workspace_id,
            nombre=nombre,
        )
    )

    if existente_id:

        if existente_id == origen_id:
            raise TypebotError(
                (
                    "SEGURIDAD: el Typebot encontrado para "
                    "la instalación es el mismo maestro."
                )
            )

        respuesta_existente = (
            client.obtener_typebot(
                existente_id
            )
        )

        if not respuesta_existente["ok"]:
            raise TypebotError(
                "No fue posible recuperar el clon existente."
            )

        clon = _extraer_typebot(
            respuesta_existente
        )

        clon_id = _validar_clon_typebot(
            origen=origen,
            clon=clon,
            nombre_esperado=nombre,
            permitir_publicado=True,
        )

        return {
            "typebot_id": clon_id,
            "creado": False,
            "recuperado": True,
            "nombre": nombre,
        }

    respuesta_clon = (
        client.duplicar_typebot(
            origen_id,
            nombre=nombre,
            workspace_id=workspace_id,
        )
    )

    if not respuesta_clon["ok"]:
        raise TypebotError(
            (
                "Typebot rechazó la duplicación. "
                f"HTTP {respuesta_clon['status']}: "
                f"{respuesta_clon['data']}"
            )
        )

    clon_inicial = _extraer_typebot(
        respuesta_clon
    )

    clon_id = str(
        clon_inicial.get("id")
        or ""
    ).strip()

    if not clon_id:
        raise TypebotError(
            "Typebot creó el clon sin devolver su ID."
        )

    try:

        respuesta_clon_completo = (
            client.obtener_typebot(
                clon_id
            )
        )

        if not respuesta_clon_completo["ok"]:
            raise TypebotError(
                (
                    "El clon fue creado, pero no pudo "
                    "ser consultado para validarlo."
                )
            )

        clon = _extraer_typebot(
            respuesta_clon_completo
        )

        clon_id = _validar_clon_typebot(
            origen=origen,
            clon=clon,
            nombre_esperado=nombre,
        )

    except Exception:

        try:
            client.eliminar_typebot(
                clon_id
            )
        except Exception:
            pass

        raise

    return {
        "typebot_id": clon_id,
        "creado": True,
        "recuperado": False,
        "nombre": nombre,
    }


# ============================================================

# ============================================================
# TNL-TYPEBOT-SALUDO-EMPRESA-V1
# ============================================================

_TYPEBOT_SALUDO_NEGOCIOLISTO = (
    "¡Hola! 👋 Bienvenido a NegocioListo."
)


def _parametrizar_saludo_empresa_typebot(
    groups,
    empresa_nombre,
):
    """
    Materializa el nombre comercial de la Empresa
    únicamente en clones privados Typebot.

    Soporta:
    - saludo heredado de Abarrotes;
    - placeholder global __EMPRESA_NOMBRE__;
    - futuras plantillas que utilicen el placeholder.
    """

    empresa_nombre = str(
        empresa_nombre
        or ""
    ).strip()

    if not empresa_nombre:
        raise TypebotError(
            (
                "No es posible parametrizar "
                "un nombre de Empresa vacío."
            )
        )

    saludo_empresa = (
        f"¡Hola! 👋 Bienvenido a "
        f"{empresa_nombre}."
    )

    cambios_saludo = 0
    cambios_placeholder = 0

    def transformar(value):

        nonlocal cambios_saludo
        nonlocal cambios_placeholder

        if isinstance(value, dict):
            return {
                key: transformar(child)
                for key, child in value.items()
            }

        if isinstance(value, list):
            return [
                transformar(child)
                for child in value
            ]

        if isinstance(value, str):

            if value == _TYPEBOT_SALUDO_NEGOCIOLISTO:
                cambios_saludo += 1
                return saludo_empresa

            ocurrencias = value.count(
                _TYPEBOT_EMPRESA_NOMBRE_PLACEHOLDER
            )

            if ocurrencias:
                cambios_placeholder += ocurrencias

                return value.replace(
                    _TYPEBOT_EMPRESA_NOMBRE_PLACEHOLDER,
                    empresa_nombre,
                )

        return value

    groups_nuevos = transformar(
        deepcopy(
            groups
            or []
        )
    )

    if cambios_saludo > 1:
        raise TypebotError(
            (
                "SEGURIDAD: múltiples saludos "
                "genéricos heredados."
            )
        )

    return (
        groups_nuevos,
        cambios_saludo + cambios_placeholder,
    )


# PARAMETRIZACION BOT_ID EN CLONES TYPEBOT
# ============================================================


_BOT_ID_BODY_KEY_RE = re.compile(
    r'"bot_id"\s*:'
)

_BOT_ID_BODY_VALUE_RE = re.compile(
    r'("bot_id"\s*:\s*)'
    r'('
    r'"(?:\\.|[^"\\])*"'
    r'|[-+]?\d+(?:\.\d+)?'
    r'|true'
    r'|false'
    r'|null'
    r')'
)


def _extraer_bot_ids_objeto(
    valor,
):
    """
    Extrae valores de claves bot_id
    dentro de dict/list.
    """

    encontrados = []

    if isinstance(valor, dict):

        for clave, item in valor.items():

            if str(clave) == "bot_id":

                encontrados.append(
                    str(item)
                )

            else:

                encontrados.extend(
                    _extraer_bot_ids_objeto(
                        item
                    )
                )

    elif isinstance(valor, list):

        for item in valor:

            encontrados.extend(
                _extraer_bot_ids_objeto(
                    item
                )
            )

    return encontrados


def _reemplazar_bot_ids_objeto(
    valor,
    bot_id,
):
    """
    Sustituye claves bot_id dentro
    de estructuras dict/list.
    """

    objetivo = str(
        bot_id
    )

    cambios = 0

    if isinstance(valor, dict):

        for clave in list(
            valor.keys()
        ):

            if str(clave) == "bot_id":

                valor[clave] = objetivo
                cambios += 1

            else:

                cambios += (
                    _reemplazar_bot_ids_objeto(
                        valor[clave],
                        objetivo,
                    )
                )

    elif isinstance(valor, list):

        for item in valor:

            cambios += (
                _reemplazar_bot_ids_objeto(
                    item,
                    objetivo,
                )
            )

    return cambios


def _extraer_bot_ids_body(
    body,
):
    """
    Extrae bot_id desde body estructurado
    o desde JSON almacenado como string.
    """

    if isinstance(
        body,
        (dict, list),
    ):

        return _extraer_bot_ids_objeto(
            body
        )

    if not isinstance(
        body,
        str,
    ):

        return []

    cantidad_claves = len(
        _BOT_ID_BODY_KEY_RE.findall(
            body
        )
    )

    if cantidad_claves == 0:

        return []

    matches = list(
        _BOT_ID_BODY_VALUE_RE.finditer(
            body
        )
    )

    if len(matches) != cantidad_claves:

        raise TypebotError(
            (
                "SEGURIDAD: body contiene bot_id "
                "que no puede auditarse "
                "completamente."
            )
        )

    valores = []

    for match in matches:

        token = match.group(2)

        try:

            valor = json.loads(
                token
            )

        except Exception as exc:

            raise TypebotError(
                "No fue posible interpretar bot_id."
            ) from exc

        valores.append(
            str(valor)
        )

    return valores


def _parametrizar_body_bot_id(
    body,
    bot_id,
):
    """
    Devuelve una copia parametrizada del body.
    """

    objetivo = str(
        bot_id
    )

    if isinstance(
        body,
        (dict, list),
    ):

        copia = deepcopy(
            body
        )

        cambios = (
            _reemplazar_bot_ids_objeto(
                copia,
                objetivo,
            )
        )

        return copia, cambios

    if not isinstance(
        body,
        str,
    ):

        return body, 0

    cantidad_claves = len(
        _BOT_ID_BODY_KEY_RE.findall(
            body
        )
    )

    if cantidad_claves == 0:

        return body, 0

    matches = list(
        _BOT_ID_BODY_VALUE_RE.finditer(
            body
        )
    )

    if len(matches) != cantidad_claves:

        raise TypebotError(
            (
                "SEGURIDAD: no es posible "
                "parametrizar todos los bot_id "
                "del body."
            )
        )

    nuevo_body, cambios = (
        _BOT_ID_BODY_VALUE_RE.subn(
            lambda match: (
                match.group(1)
                + json.dumps(
                    objetivo
                )
            ),
            body,
        )
    )

    return nuevo_body, cambios


def _auditar_bot_ids_typebot(
    typebot,
):
    """
    Obtiene exclusivamente los valores bot_id
    utilizados por webhooks.
    """

    valores = []

    for grupo in (
        typebot.get("groups")
        or []
    ):

        if not isinstance(
            grupo,
            dict,
        ):

            continue

        for bloque in (
            grupo.get("blocks")
            or []
        ):

            if not isinstance(
                bloque,
                dict,
            ):

                continue

            opciones = bloque.get(
                "options"
            )

            if not isinstance(
                opciones,
                dict,
            ):

                continue

            webhook = opciones.get(
                "webhook"
            )

            if not isinstance(
                webhook,
                dict,
            ):

                continue

            for parametro in (
                webhook.get(
                    "queryParams"
                )
                or []
            ):

                if not isinstance(
                    parametro,
                    dict,
                ):

                    continue

                if (
                    str(
                        parametro.get(
                            "key"
                        )
                        or ""
                    ).strip()
                    == "bot_id"
                ):

                    valores.append(
                        str(
                            parametro.get(
                                "value"
                            )
                        )
                    )

            if "body" in webhook:

                valores.extend(
                    _extraer_bot_ids_body(
                        webhook.get(
                            "body"
                        )
                    )
                )

    return valores


def _preparar_groups_typebot_para_bot(
    typebot,
    bot_id,
):
    """
    Genera una copia de groups con todos los
    bot_id apuntando al Bot privado.

    IMPORTANTE:
    Esta función NO modifica Typebot remoto.
    """

    objetivo = str(
        bot_id
    )

    valores_antes = (
        _auditar_bot_ids_typebot(
            typebot
        )
    )

    groups = deepcopy(
        typebot.get("groups")
        or []
    )

    cambios = 0

    for grupo in groups:

        if not isinstance(
            grupo,
            dict,
        ):

            continue

        for bloque in (
            grupo.get("blocks")
            or []
        ):

            if not isinstance(
                bloque,
                dict,
            ):

                continue

            opciones = bloque.get(
                "options"
            )

            if not isinstance(
                opciones,
                dict,
            ):

                continue

            webhook = opciones.get(
                "webhook"
            )

            if not isinstance(
                webhook,
                dict,
            ):

                continue

            for parametro in (
                webhook.get(
                    "queryParams"
                )
                or []
            ):

                if not isinstance(
                    parametro,
                    dict,
                ):

                    continue

                if (
                    str(
                        parametro.get(
                            "key"
                        )
                        or ""
                    ).strip()
                    == "bot_id"
                ):

                    parametro[
                        "value"
                    ] = objetivo

                    cambios += 1

            if "body" in webhook:

                (
                    body_nuevo,
                    cambios_body,
                ) = (
                    _parametrizar_body_bot_id(
                        webhook.get(
                            "body"
                        ),
                        objetivo,
                    )
                )

                webhook[
                    "body"
                ] = body_nuevo

                cambios += cambios_body

    simulado = {
        "groups": groups,
    }

    valores_despues = (
        _auditar_bot_ids_typebot(
            simulado
        )
    )

    if (
        len(valores_antes)
        != len(valores_despues)
    ):

        raise TypebotError(
            (
                "SEGURIDAD: cambió la cantidad "
                "de referencias bot_id."
            )
        )

    if cambios != len(
        valores_despues
    ):

        raise TypebotError(
            (
                "SEGURIDAD: no fueron "
                "parametrizadas todas las "
                "referencias bot_id."
            )
        )

    if any(
        valor != objetivo
        for valor in valores_despues
    ):

        raise TypebotError(
            (
                "SEGURIDAD: quedaron bot_id "
                "distintos al objetivo."
            )
        )

    return groups, cambios





# ============================================================
# PARAMETRIZACION BEARER TYPEBOT V1
# ============================================================


def _leer_typebot_api_key_aprovisionamiento():
    """
    Lee la clave compartida utilizada por los webhooks Typebot.

    Nunca devuelve la ruta ni el valor dentro de mensajes
    de error.
    """

    try:

        with open(
            _TYPEBOT_API_KEY_FILE,
            "r",
            encoding="utf-8",
        ) as archivo:

            valor = (
                archivo
                .read()
                .strip()
            )

    except OSError as exc:

        raise TypebotError(
            (
                "No fue posible leer la credencial "
                "de API requerida para parametrizar "
                "el Typebot."
            )
        ) from exc


    if not valor:

        raise TypebotError(
            (
                "La credencial de API requerida "
                "para parametrizar el Typebot "
                "está vacía."
            )
        )


    if (
        _TYPEBOT_API_KEY_PLACEHOLDER
        in valor
    ):

        raise TypebotError(
            (
                "La credencial de API contiene "
                "un valor reservado."
            )
        )


    if any(
        caracter.isspace()
        for caracter in valor
    ):

        raise TypebotError(
            (
                "La credencial de API tiene "
                "un formato inválido."
            )
        )


    return valor



def _auditar_placeholders_bearer_typebot(
    groups,
):
    """
    Audita únicamente __TYPEBOT_API_KEY__.

    Reglas:
    - solo puede existir dentro de un header Authorization;
    - el valor debe ser exactamente
      'Bearer __TYPEBOT_API_KEY__';
    - cualquier aparición fuera de ese contrato falla cerrado.
    """

    total_headers_validos = 0


    for grupo in (
        groups
        or []
    ):

        if not isinstance(
            grupo,
            dict,
        ):

            continue


        for bloque in (
            grupo.get("blocks")
            or []
        ):

            if not isinstance(
                bloque,
                dict,
            ):

                continue


            opciones = bloque.get(
                "options"
            )

            if not isinstance(
                opciones,
                dict,
            ):

                continue


            webhook = opciones.get(
                "webhook"
            )

            if not isinstance(
                webhook,
                dict,
            ):

                continue


            for header in (
                webhook.get("headers")
                or []
            ):

                if not isinstance(
                    header,
                    dict,
                ):

                    continue


                key = str(
                    header.get("key")
                    or ""
                ).strip()


                value = str(
                    header.get("value")
                    or ""
                )


                if (
                    _TYPEBOT_API_KEY_PLACEHOLDER
                    not in value
                ):

                    continue


                if (
                    key.lower()
                    != "authorization"
                ):

                    raise TypebotError(
                        (
                            "SEGURIDAD: el placeholder "
                            "de credencial Typebot apareció "
                            "fuera de Authorization."
                        )
                    )


                esperado = (
                    "Bearer "
                    + _TYPEBOT_API_KEY_PLACEHOLDER
                )


                if value != esperado:

                    raise TypebotError(
                        (
                            "SEGURIDAD: el placeholder "
                            "Authorization Typebot tiene "
                            "un formato inesperado."
                        )
                    )


                total_headers_validos += 1


    serializado = json.dumps(
        groups or [],
        ensure_ascii=False,
    )


    total_global = serializado.count(
        _TYPEBOT_API_KEY_PLACEHOLDER
    )


    if (
        total_global
        != total_headers_validos
    ):

        raise TypebotError(
            (
                "SEGURIDAD: existen placeholders "
                "de credencial Typebot que no "
                "pudieron auditarse completamente."
            )
        )


    return total_headers_validos



def _preparar_groups_typebot_bearer(
    groups,
    *,
    api_key=None,
):
    """
    Materializa exclusivamente:

    Bearer __TYPEBOT_API_KEY__

    dentro de headers Authorization de webhooks.

    No modifica el objeto recibido.
    """

    preparados = deepcopy(
        groups
        or []
    )


    referencias = (
        _auditar_placeholders_bearer_typebot(
            preparados
        )
    )


    if referencias == 0:

        return preparados, 0


    if api_key is None:

        api_key = (
            _leer_typebot_api_key_aprovisionamiento()
        )


    api_key = str(
        api_key
        or ""
    ).strip()


    if not api_key:

        raise TypebotError(
            (
                "No existe credencial Typebot "
                "válida para parametrizar "
                "el clon."
            )
        )


    if (
        _TYPEBOT_API_KEY_PLACEHOLDER
        in api_key
    ):

        raise TypebotError(
            (
                "La credencial Typebot contiene "
                "un valor reservado."
            )
        )


    if any(
        caracter.isspace()
        for caracter in api_key
    ):

        raise TypebotError(
            (
                "La credencial Typebot tiene "
                "un formato inválido."
            )
        )


    cambios = 0


    for grupo in preparados:

        if not isinstance(
            grupo,
            dict,
        ):

            continue


        for bloque in (
            grupo.get("blocks")
            or []
        ):

            if not isinstance(
                bloque,
                dict,
            ):

                continue


            opciones = bloque.get(
                "options"
            )

            if not isinstance(
                opciones,
                dict,
            ):

                continue


            webhook = opciones.get(
                "webhook"
            )

            if not isinstance(
                webhook,
                dict,
            ):

                continue


            for header in (
                webhook.get("headers")
                or []
            ):

                if not isinstance(
                    header,
                    dict,
                ):

                    continue


                key = str(
                    header.get("key")
                    or ""
                ).strip()


                value = str(
                    header.get("value")
                    or ""
                )


                if (
                    key.lower()
                    == "authorization"
                    and
                    value
                    ==
                    (
                        "Bearer "
                        + _TYPEBOT_API_KEY_PLACEHOLDER
                    )
                ):

                    header["value"] = (
                        "Bearer "
                        + api_key
                    )

                    cambios += 1


    if cambios != referencias:

        raise TypebotError(
            (
                "SEGURIDAD: no fueron "
                "materializadas todas las "
                "credenciales Typebot."
            )
        )


    restantes = (
        _auditar_placeholders_bearer_typebot(
            preparados
        )
    )


    if restantes != 0:

        raise TypebotError(
            (
                "SEGURIDAD: quedaron placeholders "
                "de credencial Typebot después "
                "de parametrizar."
            )
        )


    return preparados, cambios




# ============================================================
# TNL-TYPEBOT-EMPRESA-TEXTOS-V1
# PARAMETRIZACION DE TEXTOS VISIBLES DE EMPRESA
# ============================================================

_TYPEBOT_EMPRESA_NOMBRE_PLACEHOLDER = "__EMPRESA_NOMBRE__"
_TYPEBOT_EMPRESA_DIRECCION_PLACEHOLDER = (
    "__EMPRESA_DIRECCION__"
)

_TYPEBOT_EMPRESA_TELEFONO_PLACEHOLDER = (
    "__EMPRESA_TELEFONO__"
)


def _construir_direccion_empresa_typebot(
    empresa,
):
    """
    Construye la dirección visible del Typebot
    exclusivamente con datos persistidos en Empresa.
    """

    if (
        empresa is None
        or not empresa.pk
    ):

        raise TypebotError(
            "No existe Empresa válida para "
            "parametrizar su dirección."
        )


    campos = {
        "calle":
            str(
                empresa.domicilio_calle
                or ""
            ).strip(),

        "numero_exterior":
            str(
                empresa.domicilio_numero_exterior
                or ""
            ).strip(),

        "numero_interior":
            str(
                empresa.domicilio_numero_interior
                or ""
            ).strip(),

        "colonia":
            str(
                empresa.domicilio_colonia
                or ""
            ).strip(),

        "codigo_postal":
            str(
                empresa.domicilio_codigo_postal
                or ""
            ).strip(),

        "municipio":
            str(
                empresa.domicilio_municipio
                or ""
            ).strip(),

        "ciudad":
            str(
                empresa.domicilio_ciudad
                or ""
            ).strip(),

        "estado":
            str(
                empresa.domicilio_estado
                or ""
            ).strip(),

        "pais":
            str(
                empresa.domicilio_pais
                or ""
            ).strip(),
    }


    requeridos = (
        "calle",
        "numero_exterior",
        "colonia",
        "codigo_postal",
        "municipio",
        "ciudad",
        "estado",
        "pais",
    )


    faltantes = [
        nombre
        for nombre in requeridos
        if not campos[nombre]
    ]


    if faltantes:

        raise TypebotError(
            (
                "La Empresa no tiene domicilio "
                "completo para parametrizar Typebot. "
                "Faltan campos obligatorios."
            )
        )


    primera_linea = (
        campos["calle"]
        +
        " "
        +
        campos["numero_exterior"]
    )


    if campos[
        "numero_interior"
    ]:

        primera_linea += (
            " Int. "
            +
            campos[
                "numero_interior"
            ]
        )


    partes = [
        primera_linea,
        campos["colonia"],
        "C.P. "
        +
        campos["codigo_postal"],
    ]


    # Evitar duplicar municipio/ciudad cuando
    # ambos campos contienen exactamente lo mismo.
    ubicaciones = []


    for valor in (
        campos["municipio"],
        campos["ciudad"],
        campos["estado"],
        campos["pais"],
    ):

        if (
            valor
            and
            valor.casefold()
            not in {
                existente.casefold()
                for existente
                in ubicaciones
            }
        ):

            ubicaciones.append(
                valor
            )


    partes.extend(
        ubicaciones
    )


    return ", ".join(
        partes
    )


def _construir_telefono_visible_empresa_typebot(
    empresa,
):
    """
    Devuelve un teléfono visible canónico.

    Se reutiliza el mismo validador usado por
    el Redirect WhatsApp para evitar aceptar
    un teléfono que WhatsApp rechazaría.
    """

    if (
        empresa is None
        or not empresa.pk
    ):

        raise TypebotError(
            "No existe Empresa válida para "
            "parametrizar su teléfono."
        )


    normalizado = (
        _normalizar_telefono_whatsapp_mexico(
            empresa.telefono
        )
    )


    return (
        "+"
        +
        normalizado
    )


def _reemplazar_placeholders_empresa_objeto(
    value,
    replacements,
):
    """
    Sustitución recursiva únicamente sobre
    valores string. Nunca altera claves,
    IDs, edges ni estructura del Typebot.
    """

    cambios = 0


    if isinstance(
        value,
        dict,
    ):

        resultado = {}


        for key, child in (
            value.items()
        ):

            (
                resultado[key],
                cambios_child,
            ) = (
                _reemplazar_placeholders_empresa_objeto(
                    child,
                    replacements,
                )
            )


            cambios += (
                cambios_child
            )


        return (
            resultado,
            cambios,
        )


    if isinstance(
        value,
        list,
    ):

        resultado = []


        for child in value:

            (
                child_nuevo,
                cambios_child,
            ) = (
                _reemplazar_placeholders_empresa_objeto(
                    child,
                    replacements,
                )
            )


            resultado.append(
                child_nuevo
            )

            cambios += (
                cambios_child
            )


        return (
            resultado,
            cambios,
        )


    if isinstance(
        value,
        str,
    ):

        nuevo = value


        for placeholder, real in (
            replacements.items()
        ):

            ocurrencias = (
                nuevo.count(
                    placeholder
                )
            )


            if ocurrencias:

                nuevo = nuevo.replace(
                    placeholder,
                    real,
                )

                cambios += (
                    ocurrencias
                )


        return (
            nuevo,
            cambios,
        )


    return (
        value,
        0,
    )


def _auditar_placeholders_empresa_typebot(
    groups,
):
    """
    Cuenta placeholders empresariales conocidos.
    """

    serializado = json.dumps(
        groups
        or [],
        ensure_ascii=False,
    )


    return {
        _TYPEBOT_EMPRESA_DIRECCION_PLACEHOLDER:
            serializado.count(
                _TYPEBOT_EMPRESA_DIRECCION_PLACEHOLDER
            ),

        _TYPEBOT_EMPRESA_TELEFONO_PLACEHOLDER:
            serializado.count(
                _TYPEBOT_EMPRESA_TELEFONO_PLACEHOLDER
            ),
    }


def _preparar_textos_empresa_typebot(
    groups,
    empresa,
):
    """
    Materializa únicamente placeholders
    empresariales visibles en una copia
    independiente de groups.
    """

    direccion = (
        _construir_direccion_empresa_typebot(
            empresa
        )
    )

    telefono = (
        _construir_telefono_visible_empresa_typebot(
            empresa
        )
    )


    replacements = {
        _TYPEBOT_EMPRESA_DIRECCION_PLACEHOLDER:
            direccion,

        _TYPEBOT_EMPRESA_TELEFONO_PLACEHOLDER:
            telefono,
    }


    auditoria_antes = (
        _auditar_placeholders_empresa_typebot(
            groups
        )
    )


    total_antes = sum(
        auditoria_antes.values()
    )


    if total_antes == 0:

        return (
            deepcopy(
                groups
                or []
            ),
            0,
        )


    (
        preparados,
        cambios,
    ) = (
        _reemplazar_placeholders_empresa_objeto(
            deepcopy(
                groups
                or []
            ),
            replacements,
        )
    )


    auditoria_despues = (
        _auditar_placeholders_empresa_typebot(
            preparados
        )
    )


    if any(
        auditoria_despues.values()
    ):

        raise TypebotError(
            (
                "SEGURIDAD: el Typebot conserva "
                "placeholders empresariales "
                "después de parametrizarlo."
            )
        )


    if cambios != total_antes:

        raise TypebotError(
            (
                "SEGURIDAD: la cantidad de "
                "placeholders empresariales "
                "procesados es inconsistente."
            )
        )


    return (
        preparados,
        cambios,
    )


def _validar_textos_empresa_typebot(
    groups,
    empresa,
    referencias,
):
    """
    Certifica el resultado empresarial después
    del PATCH remoto.
    """

    referencias = int(
        referencias
        or 0
    )


    auditoria = (
        _auditar_placeholders_empresa_typebot(
            groups
        )
    )


    if any(
        auditoria.values()
    ):

        raise TypebotError(
            (
                "SEGURIDAD: el clon final conserva "
                "placeholders empresariales."
            )
        )


    if referencias <= 0:

        return 0


    direccion = (
        _construir_direccion_empresa_typebot(
            empresa
        )
    )

    telefono = (
        _construir_telefono_visible_empresa_typebot(
            empresa
        )
    )


    serializado = json.dumps(
        groups
        or [],
        ensure_ascii=False,
    )


    direccion_esperada = (
        "📍 Dirección: "
        +
        direccion
    )

    telefono_esperado = (
        "📱 WhatsApp: "
        +
        telefono
    )


    if (
        direccion_esperada
        not in
        serializado
    ):

        raise TypebotError(
            (
                "SEGURIDAD: el clon final no "
                "contiene la dirección de su Empresa."
            )
        )


    if (
        telefono_esperado
        not in
        serializado
    ):

        raise TypebotError(
            (
                "SEGURIDAD: el clon final no "
                "contiene el teléfono de su Empresa."
            )
        )


    return referencias

def _normalizar_telefono_whatsapp_mexico(
    telefono,
):
    """
    Normaliza el teléfono empresarial para
    enlaces WhatsApp de NegocioListo México.

    Reglas aceptadas:
    - 10 dígitos nacionales -> 52 + teléfono;
    - 12 dígitos iniciando en 52 -> se conservan.

    Cualquier otro formato se rechaza.
    """

    digitos = re.sub(
        r"\D",
        "",
        str(
            telefono
            or ""
        ),
    )

    if len(digitos) == 10:

        return (
            "52"
            + digitos
        )

    if (
        len(digitos) == 12
        and digitos.startswith("52")
    ):

        return digitos

    raise TypebotError(
        (
            "Empresa.telefono no tiene "
            "un formato válido para WhatsApp. "
            "Se requieren 10 dígitos nacionales "
            "o 12 dígitos iniciando en 52."
        )
    )


def _construir_url_whatsapp_empresa(
    empresa,
):
    """
    Construye el Redirect WhatsApp usando
    exclusivamente datos de la Empresa.
    """

    if (
        empresa is None
        or not empresa.pk
    ):

        raise TypebotError(
            "No existe Empresa válida para parametrizar WhatsApp."
        )

    nombre = str(
        empresa.nombre
        or ""
    ).strip()

    if not nombre:

        raise TypebotError(
            "La Empresa no tiene nombre para parametrizar WhatsApp."
        )

    telefono = (
        _normalizar_telefono_whatsapp_mexico(
            empresa.telefono
        )
    )

    mensaje = (
        f"Hola {nombre}, "
        "quiero información sobre sus servicios"
    )

    query = urlencode(
        {
            "phone": telefono,
            "text": mensaje,
        }
    )

    return (
        "https://api.whatsapp.com/send?"
        + query
    )


def _localizar_redirects_whatsapp_empresa(
    groups,
):
    """
    Localiza únicamente el Redirect WhatsApp
    del grupo estándar de atención humana.
    """

    encontrados = []

    for group in (
        groups
        or []
    ):

        if not isinstance(
            group,
            dict,
        ):
            continue

        titulo = str(
            group.get("title")
            or ""
        ).strip()

        if titulo != (
            "Soporte - Atención humana"
        ):
            continue

        for block in (
            group.get("blocks")
            or []
        ):

            if not isinstance(
                block,
                dict,
            ):
                continue

            if str(
                block.get("type")
                or ""
            ).strip().lower() != "redirect":
                continue

            options = (
                block.get("options")
                or {}
            )

            if not isinstance(
                options,
                dict,
            ):
                continue

            url = str(
                options.get("url")
                or ""
            ).strip()

            url_lower = (
                url.lower()
            )

            if (
                "api.whatsapp.com/" not in url_lower
                and "wa.me/" not in url_lower
            ):
                continue

            encontrados.append(
                block
            )

    return encontrados


def _preparar_redirect_whatsapp_empresa(
    groups,
    empresa,
):
    """
    Parametriza exclusivamente el Redirect
    WhatsApp empresarial dentro de una copia
    de groups.

    Si la plantilla no contiene ese Redirect,
    no realiza ninguna modificación.
    """

    copia = deepcopy(
        groups
        or []
    )

    encontrados = (
        _localizar_redirects_whatsapp_empresa(
            copia
        )
    )

    if not encontrados:

        return (
            copia,
            0,
            0,
        )

    if len(encontrados) != 1:

        raise TypebotError(
            (
                "SEGURIDAD: se esperaba como máximo "
                "un Redirect WhatsApp empresarial."
            )
        )

    url_esperada = (
        _construir_url_whatsapp_empresa(
            empresa
        )
    )

    block = encontrados[0]

    options = deepcopy(
        block.get("options")
        or {}
    )

    url_actual = str(
        options.get("url")
        or ""
    )

    cambios = 0

    if url_actual != url_esperada:

        options["url"] = (
            url_esperada
        )

        block["options"] = (
            options
        )

        cambios = 1

    return (
        copia,
        1,
        cambios,
    )


def _validar_redirect_whatsapp_empresa(
    groups,
    empresa,
):
    """
    Comprueba después del PATCH que el clon
    conserva exactamente el Redirect esperado.
    """

    encontrados = (
        _localizar_redirects_whatsapp_empresa(
            groups
        )
    )

    if not encontrados:

        return 0

    if len(encontrados) != 1:

        raise TypebotError(
            (
                "SEGURIDAD: el clon contiene "
                "más de un Redirect WhatsApp empresarial."
            )
        )

    url_esperada = (
        _construir_url_whatsapp_empresa(
            empresa
        )
    )

    url_actual = str(
        (
            encontrados[0]
            .get("options")
            or {}
        ).get("url")
        or ""
    )

    if url_actual != url_esperada:

        raise TypebotError(
            (
                "SEGURIDAD: el Redirect WhatsApp "
                "del clon no corresponde a su Empresa."
            )
        )

    return 1


def _parametrizar_typebot_para_bot(
    *,
    client,
    typebot_id,
    bot,
    plantilla_maestra,
):
    """
    Parametriza exclusivamente un clon Typebot
    con datos reales del Bot y su Empresa.

    IMPORTANTE:
    - nunca permite modificar el Typebot maestro;
    - comprueba la asociación local;
    - modifica groups y variables técnicas de sesión;
    - valida nuevamente el clon después del PATCH.
    """

    typebot_id = str(
        typebot_id
        or ""
    ).strip()

    if not typebot_id:

        raise TypebotError(
            "No existe Typebot ID para parametrizar."
        )


    if (
        bot is None
        or not bot.pk
    ):

        raise TypebotError(
            "No existe Bot privado válido."
        )


    maestro_id = str(
        plantilla_maestra
        .identificador_externo
        or ""
    ).strip()


    # ========================================================
    # PROTECCION DEL MAESTRO
    # ========================================================

    if (
        maestro_id
        and typebot_id == maestro_id
    ):

        raise TypebotError(
            (
                "SEGURIDAD: se intentó "
                "parametrizar el Typebot maestro."
            )
        )


    # ========================================================
    # VALIDAR ASOCIACION LOCAL
    # ========================================================

    bot_externo = str(
        bot.identificador_externo
        or ""
    ).strip()

    if (
        bot_externo
        and bot_externo != typebot_id
    ):

        raise TypebotError(
            (
                "SEGURIDAD: el Bot local "
                "está asociado a otro Typebot."
            )
        )


    # ========================================================
    # LEER CLON ANTES DEL PATCH
    # ========================================================

    respuesta = (
        client.obtener_typebot(
            typebot_id
        )
    )

    if not respuesta["ok"]:

        raise TypebotError(
            (
                "No fue posible obtener el clon "
                "antes de parametrizarlo. "
                f"HTTP {respuesta['status']}."
            )
        )


    clon = _extraer_typebot(
        respuesta
    )


    if clon.get(
        "isArchived"
    ) is True:

        raise TypebotError(
            "El clon está archivado."
        )


    clon_id = str(
        clon.get("id")
        or ""
    ).strip()

    if clon_id != typebot_id:

        raise TypebotError(
            (
                "SEGURIDAD: Typebot devolvió "
                "un ID diferente al solicitado."
            )
        )


    # ========================================================
    # SNAPSHOT ESTRUCTURAL
    # ========================================================

    cantidades_antes = {
        campo: len(
            clon.get(campo)
            or []
        )
        for campo in (
            "groups",
            "variables",
            "edges",
            "events",
        )
    }


    valores_antes = (
        _auditar_bot_ids_typebot(
            clon
        )
    )


    # ========================================================
    # PREPARAR GROUPS
    # ========================================================

    groups_nuevos, referencias = (
        _preparar_groups_typebot_para_bot(
            clon,
            bot.pk,
        )
    )


    (
        groups_nuevos,
        textos_empresa_referencias,
    ) = (
        _preparar_textos_empresa_typebot(
            groups_nuevos,
            bot.empresa,
        )
    )


    (
        groups_nuevos,
        redirects_empresa,
        redirects_cambiados,
    ) = (
        _preparar_redirect_whatsapp_empresa(
            groups_nuevos,
            bot.empresa,
        )
    )


    (
        groups_nuevos,
        bearer_cambiados,
    ) = (
        _preparar_groups_typebot_bearer(
            groups_nuevos,
        )
    )


    # ========================================================
    # IDENTIDAD CONVERSACIONAL TYPEBOT
    # TNL-TYPEBOT-CONVERSATION-IDENTITY-V1
    # ========================================================

    (
        variables_nuevas,
        variables_tecnicas_agregadas,
    ) = (
        _preparar_variables_tecnicas_typebot(
            clon
        )
    )


    (
        groups_nuevos,
        webhooks_ia_identidad,
        webhooks_ia_identidad_cambiados,
    ) = (
        _preparar_identidad_ia_typebot(
            groups_nuevos
        )
    )


    # ========================================================
    # SALUDO MULTIEMPRESA
    # ========================================================

    (
        groups_nuevos,
        saludo_empresa_cambios,
    ) = (
        _parametrizar_saludo_empresa_typebot(
            groups_nuevos,
            bot.empresa.nombre,
        )
    )


    groups_originales = (
        clon.get("groups")
        or []
    )


    variables_originales = (
        clon.get("variables")
        or []
    )

    clon_proyectado = deepcopy(
        clon
    )

    clon_proyectado["groups"] = (
        groups_nuevos
    )

    clon_proyectado["variables"] = (
        variables_nuevas
    )

    _validar_identidad_ia_typebot(
        clon_proyectado
    )

    _validar_invariantes_imagenes_producto_typebot(
        clon_proyectado,
        contexto="clon Typebot preparado",
    )


    # "referencias" representa la cantidad de
    # referencias bot_id procesadas, no la
    # cantidad real de valores modificados.
    #
    # La decisión de ejecutar PATCH debe
    # depender exclusivamente del resultado
    # estructural final.
    if (
        groups_nuevos == groups_originales
        and
        variables_nuevas == variables_originales
    ):

        return {
            "actualizado": False,
            "referencias": 0,
            "valores_antes": [],
            "redirects_empresa": (
                redirects_empresa
            ),
            "redirects_cambiados": 0,
            "bearer_cambiados": 0,
            "variables_tecnicas_agregadas": [],
            "webhooks_ia_identidad": (
                webhooks_ia_identidad
            ),
            "webhooks_ia_identidad_cambiados": 0,
        }


    if referencias != len(
        valores_antes
    ):

        raise TypebotError(
            (
                "SEGURIDAD: la cantidad "
                "de referencias preparadas "
                "no coincide con la auditoría."
            )
        )


    # ========================================================
    # PATCH EXCLUSIVAMENTE AL CLON
    # ========================================================

    actualizacion = (
        client.actualizar_typebot(
            typebot_id,
            typebot={
                "groups": groups_nuevos,
                "variables": variables_nuevas,
            },
            overwrite=True,
        )
    )


    if not actualizacion["ok"]:

        raise TypebotError(
            (
                "Typebot rechazó la "
                "parametrización del clon. "
                f"HTTP {actualizacion['status']}."
            )
        )


    # ========================================================
    # RELECTURA OBLIGATORIA
    # ========================================================

    comprobacion = (
        client.obtener_typebot(
            typebot_id
        )
    )

    if not comprobacion["ok"]:

        raise TypebotError(
            (
                "El clon fue actualizado, "
                "pero no pudo comprobarse."
            )
        )


    clon_final = _extraer_typebot(
        comprobacion
    )

    _validar_invariantes_imagenes_producto_typebot(
        clon_final,
        contexto="clon Typebot final",
    )


    clon_final_id = str(
        clon_final.get("id")
        or ""
    ).strip()

    if clon_final_id != typebot_id:

        raise TypebotError(
            (
                "SEGURIDAD: el Typebot "
                "comprobado tiene otro ID."
            )
        )


    if clon_final.get(
        "isArchived"
    ) is True:

        raise TypebotError(
            (
                "SEGURIDAD: el clon quedó "
                "archivado inesperadamente."
            )
        )


    # ========================================================
    # VALIDAR ESTRUCTURA
    # ========================================================

    cantidades_despues = {
        campo: len(
            clon_final.get(campo)
            or []
        )
        for campo in (
            "groups",
            "variables",
            "edges",
            "events",
        )
    }


    cantidades_esperadas = dict(
        cantidades_antes
    )

    cantidades_esperadas[
        "variables"
    ] = len(
        variables_nuevas
    )

    if (
        cantidades_esperadas
        != cantidades_despues
    ):

        raise TypebotError(
            (
                "SEGURIDAD: la estructura "
                "del Typebot cambió después "
                "de parametrizar bot_id."
            )
        )


    _validar_variables_tecnicas_clon_typebot(
        clon,
        clon_final,
    )

    _validar_identidad_ia_typebot(
        clon_final
    )


    # ========================================================
    # VALIDAR BOT_ID FINAL
    # ========================================================

    valores_finales = (
        _auditar_bot_ids_typebot(
            clon_final
        )
    )


    if len(
        valores_finales
    ) != referencias:

        raise TypebotError(
            (
                "SEGURIDAD: cambió la cantidad "
                "de referencias bot_id después "
                "del PATCH."
            )
        )


    objetivo = str(
        bot.pk
    )


    if any(
        valor != objetivo
        for valor in valores_finales
    ):

        raise TypebotError(
            (
                "SEGURIDAD: el clon conserva "
                "bot_id que no pertenecen "
                "al Bot privado."
            )
        )


    _validar_textos_empresa_typebot(
        clon_final.get(
            "groups"
        )
        or [],
        bot.empresa,
        textos_empresa_referencias,
    )


    bearer_placeholders_finales = (
        _auditar_placeholders_bearer_typebot(
            clon_final.get(
                "groups"
            )
            or []
        )
    )


    if bearer_placeholders_finales != 0:

        raise TypebotError(
            (
                "SEGURIDAD: el clon final conserva "
                "placeholders de credencial Typebot."
            )
        )


    redirects_finales = 0

    if redirects_empresa:

        redirects_finales = (
            _validar_redirect_whatsapp_empresa(
                clon_final.get(
                    "groups"
                )
                or [],
                bot.empresa,
            )
        )

        if (
            redirects_finales
            != redirects_empresa
        ):

            raise TypebotError(
                (
                    "SEGURIDAD: cambió la cantidad "
                    "de Redirects WhatsApp "
                    "después del PATCH."
                )
            )


    return {
        "actualizado": True,
        "referencias": referencias,
        "valores_antes": sorted(
            set(valores_antes)
        ),
        "redirects_empresa": (
            redirects_finales
        ),
        "redirects_cambiados": (
            redirects_cambiados
        ),
        "bearer_cambiados": (
            bearer_cambiados
        ),
        "variables_tecnicas_agregadas": list(
            variables_tecnicas_agregadas
        ),
        "webhooks_ia_identidad": (
            webhooks_ia_identidad
        ),
        "webhooks_ia_identidad_cambiados": (
            webhooks_ia_identidad_cambiados
        ),
    }





# =============================================================================
# TNL-RESTAURANTE-LOCAL-DEFAULTS-V1
# =============================================================================

def _aprovisionar_restaurante_local(
    *,
    empresa,
    plantilla_maestra,
    catalogo,
):
    """
    Garantiza los recursos locales mínimos
    de una instalación Restaurante.

    Es idempotente y no altera otras verticales.
    """

    if (
        str(
            getattr(
                plantilla_maestra,
                "tipo",
                "",
            )
            or ""
        )
        != "restaurante"
    ):
        return {
            "aplica": False,
            "configuracion_id": None,
            "configuracion_creada": False,
            "categoria_id": None,
            "categoria_creada": False,
        }

    if catalogo is None:
        raise ValueError(
            "La plantilla Restaurante requiere catálogo."
        )

    from core.models import (
        CategoriaProducto,
        ConfiguracionRestaurante,
    )

    configuracion, config_creada = (
        ConfiguracionRestaurante.objects
        .get_or_create(
            empresa=empresa,
        )
    )

    categoria, categoria_creada = (
        CategoriaProducto.objects
        .get_or_create(
            catalogo=catalogo,
            nombre="Menú general",
            defaults={
                "descripcion": (
                    "Categoría general creada automáticamente "
                    "para el menú del restaurante."
                ),
                "orden": 0,
                "activa": True,
            },
        )
    )

    if not categoria.activa:
        categoria.activa = True
        categoria.save()

    return {
        "aplica": True,
        "configuracion_id": configuracion.id,
        "configuracion_creada": bool(config_creada),
        "categoria_id": categoria.id,
        "categoria_creada": bool(categoria_creada),
    }


def _crear_recursos_operativos(
    *,
    instalacion,
    empresa,
    plantilla_maestra,
    typebot_id="",
):
    """
    Crea la instancia privada de la plantilla y sus recursos.

    IMPORTANTE:
    Esta función debe ejecutarse dentro de transaction.atomic().
    """

    configuracion = (
        plantilla_maestra.configuracion
        if isinstance(
            plantilla_maestra.configuracion,
            dict,
        )
        else {}
    )

    nombre_plantilla = _nombre_limitado(
        Plantilla,
        "nombre",
        (
            f"{plantilla_maestra.nombre} "
            f"v{plantilla_maestra.version}"
        ),
    )

    plantilla = Plantilla.objects.create(
        empresa=empresa,
        nombre=nombre_plantilla,
        tipo=plantilla_maestra.tipo,
        descripcion=(
            plantilla_maestra.descripcion
            or ""
        ),
        identificador_externo=typebot_id,
        activa=True,
    )

    variables_maestras = (
        plantilla_maestra.variables
        .filter(
            activa=True,
        )
        .order_by(
            "orden",
            "id",
        )
    )

    for variable_maestra in variables_maestras:

        Variable.objects.create(
            plantilla=plantilla,
            clave=variable_maestra.clave,
            valor=(
                variable_maestra.valor_default
                or ""
            ),
            descripcion=(
                variable_maestra.descripcion
                or ""
            ),
            activa=True,
        )

    crear_bot = configuracion.get(
        "crear_bot",
        True,
    )

    bot = None

    if crear_bot:

        nombre_bot = configuracion.get(
            "nombre_bot",
            (
                f"Bot {plantilla_maestra.nombre}"
            ),
        )

        bot = Bot.objects.create(
            empresa=empresa,
            plantilla=plantilla,
            nombre=_nombre_limitado(
                Bot,
                "nombre",
                nombre_bot,
            ),
            identificador_externo=typebot_id,
            activo=True,
        )

    canal = None
    canal_creado = False

    if bot is not None:

        canal, canal_creado = (
            _asegurar_canal_whatsapp(
                bot
            )
        )

    crear_catalogo = configuracion.get(
        "crear_catalogo",
        True,
    )

    catalogo = None

    if crear_catalogo:

        nombre_catalogo = (
            configuracion.get(
                "nombre_catalogo",
                (
                    f"Catálogo "
                    f"{plantilla_maestra.nombre}"
                ),
            )
        )

        catalogo = Catalogo.objects.create(
            empresa=empresa,
            plantilla=plantilla,
            nombre=_nombre_limitado(
                Catalogo,
                "nombre",
                nombre_catalogo,
            ),
            descripcion=(
                "Catálogo aprovisionado "
                f"desde {plantilla_maestra}."
            ),
            moneda=_moneda_catalogo(
                configuracion
            ),
            identificador_externo="",
            activo=True,
        )

    _aprovisionar_restaurante_local(
        empresa=empresa,
        plantilla_maestra=plantilla_maestra,
        catalogo=catalogo,
    )

    instalacion.plantilla = plantilla
    instalacion.version_instalada = (
        plantilla_maestra.version
    )
    instalacion.estado = (
        InstalacionPlantilla.Estado.LISTA
    )
    instalacion.ultimo_error = ""
    instalacion.completada_en = timezone.now()

    instalacion.save(
        update_fields=[
            "plantilla",
            "version_instalada",
            "estado",
            "ultimo_error",
            "completada_en",
            "actualizado_en",
        ]
    )

    return {
        "instalacion": instalacion,
        "plantilla": plantilla,
        "bot": bot,
        "canal": canal,
        "canal_creado": canal_creado,
        "catalogo": catalogo,
    }



def provisionar_empresa_desde_plantilla(
    *,
    empresa_id,
    licencia_id,
    plantilla_maestra_id,
    clave_idempotencia=None,
):
    """
    Aprovisiona una plantilla maestra para una empresa.

    Características:
    - valida Empresa, Licencia y PlantillaMaestra;
    - evita instalaciones locales duplicadas;
    - permite reintentar instalaciones en ERROR;
    - conserva compatibilidad con maestras sin Typebot;
    - clona un Typebot maestro cuando existe identificador_externo;
    - usa nombre determinista para idempotencia externa;
    - recupera clones de ejecuciones interrumpidas;
    - vincula el mismo Typebot a Plantilla y Bot;
    - permite completar instalaciones LISTA antiguas sin Typebot;
    - hace rollback local mediante transaction.atomic();
    - archiva el clon nuevo si falla la persistencia local;
    - todavía no conecta Evolution API.
    """

    modo_completar_typebot = False

    # ========================================================
    # FASE 1
    # Reservar o localizar la instalación.
    # ========================================================

    with transaction.atomic():

        empresa = (
            Empresa.objects
            .select_for_update()
            .get(
                pk=empresa_id
            )
        )

        licencia = (
            Licencia.objects
            .select_for_update()
            .get(
                pk=licencia_id
            )
        )

        plantilla_maestra = (
            PlantillaMaestra.objects
            .select_for_update()
            .get(
                pk=plantilla_maestra_id
            )
        )

        _validar_empresa(
            empresa
        )

        _validar_licencia(
            licencia,
            empresa,
        )

        _validar_plantilla_maestra(
            plantilla_maestra
        )

        instalacion = (
            InstalacionPlantilla.objects
            .select_for_update()
            .filter(
                empresa=empresa,
                plantilla_maestra=(
                    plantilla_maestra
                ),
            )
            .first()
        )

        if instalacion:

            if (
                instalacion.estado
                == InstalacionPlantilla.Estado.LISTA
            ):

                # --------------------------------------------
                # Compatibilidad:
                # si la maestra todavía no usa Typebot,
                # conservamos exactamente la idempotencia V1.
                # --------------------------------------------

                if not _requiere_typebot(
                    plantilla_maestra
                ):

                    plantilla_actual = (
                        instalacion.plantilla
                    )

                    bot_actual = (
                        plantilla_actual
                        .bots
                        .first()
                        if plantilla_actual
                        else None
                    )

                    canal, canal_creado = (
                        _asegurar_canal_whatsapp(
                            bot_actual
                        )
                    )

                    return {
                        "instalacion": instalacion,
                        "plantilla": plantilla_actual,
                        "bot": bot_actual,
                        "canal": canal,
                        "canal_creado": canal_creado,
                        "catalogo": (
                            plantilla_actual
                            .catalogos
                            .first()
                            if plantilla_actual
                            else None
                        ),
                        "idempotente": (
                            not canal_creado
                        ),
                    }

                if not instalacion.plantilla_id:
                    raise ValidationError(
                        (
                            "La instalación está LISTA, "
                            "pero no tiene Plantilla asociada."
                        )
                    )

                plantilla_actual = (
                    instalacion.plantilla
                )

                bot_actual = (
                    plantilla_actual
                    .bots
                    .first()
                )

                if bot_actual is None:
                    raise ValidationError(
                        (
                            "La instalación está LISTA, "
                            "pero no tiene Bot asociado."
                        )
                    )

                plantilla_externo = str(
                    plantilla_actual
                    .identificador_externo
                    or ""
                ).strip()

                bot_externo = str(
                    bot_actual
                    .identificador_externo
                    or ""
                ).strip()

                # Ya tiene Typebot correctamente asociado.
                if (
                    plantilla_externo
                    and bot_externo
                ):

                    if (
                        plantilla_externo
                        != bot_externo
                    ):
                        raise ValidationError(
                            (
                                "Plantilla y Bot tienen "
                                "Typebot IDs diferentes. "
                                "Debe revisarse manualmente."
                            )
                        )

                    canal, canal_creado = (
                        _asegurar_canal_whatsapp(
                            bot_actual
                        )
                    )

                    return {
                        "instalacion": instalacion,
                        "plantilla": plantilla_actual,
                        "bot": bot_actual,
                        "canal": canal,
                        "canal_creado": canal_creado,
                        "catalogo": (
                            plantilla_actual
                            .catalogos
                            .first()
                        ),
                        "idempotente": (
                            not canal_creado
                        ),
                    }

                # Asociación parcial: no asumir cuál es correcta.
                if (
                    plantilla_externo
                    or bot_externo
                ):
                    raise ValidationError(
                        (
                            "Existe una asociación Typebot parcial. "
                            "Debe revisarse manualmente antes "
                            "de continuar."
                        )
                    )

                # Instalación histórica local-only.
                # La bloqueamos temporalmente para que dos
                # solicitudes no creen clones simultáneos.
                modo_completar_typebot = True

                instalacion.estado = (
                    InstalacionPlantilla
                    .Estado
                    .APROVISIONANDO
                )
                instalacion.ultimo_error = ""

                instalacion.save(
                    update_fields=[
                        "estado",
                        "ultimo_error",
                        "actualizado_en",
                    ]
                )

            elif (
                instalacion.estado
                == InstalacionPlantilla.Estado.APROVISIONANDO
            ):
                raise ValidationError(
                    (
                        "La instalación ya se encuentra "
                        "en proceso de aprovisionamiento."
                    )
                )

            else:

                if instalacion.plantilla_id:
                    raise ValidationError(
                        (
                            "Existe una instalación incompleta "
                            "con una plantilla operativa asociada. "
                            "Debe revisarse manualmente antes "
                            "de reintentar."
                        )
                    )

                instalacion.licencia = licencia
                instalacion.version_instalada = (
                    plantilla_maestra.version
                )
                instalacion.estado = (
                    InstalacionPlantilla
                    .Estado
                    .APROVISIONANDO
                )
                instalacion.ultimo_error = ""
                instalacion.completada_en = None

                instalacion.save(
                    update_fields=[
                        "licencia",
                        "version_instalada",
                        "estado",
                        "ultimo_error",
                        "completada_en",
                        "actualizado_en",
                    ]
                )

        else:

            create_kwargs = {
                "empresa": empresa,
                "licencia": licencia,
                "plantilla_maestra": (
                    plantilla_maestra
                ),
                "version_instalada": (
                    plantilla_maestra.version
                ),
                "estado": (
                    InstalacionPlantilla
                    .Estado
                    .APROVISIONANDO
                ),
            }

            if clave_idempotencia is not None:
                create_kwargs[
                    "clave_idempotencia"
                ] = clave_idempotencia

            instalacion = (
                InstalacionPlantilla.objects.create(
                    **create_kwargs
                )
            )

        instalacion_id = instalacion.id

    # ========================================================
    # FASE 2
    # Typebot externo + persistencia local.
    # ========================================================

    client = None

    typebot_info = {
        "typebot_id": "",
        "creado": False,
        "recuperado": False,
        "nombre": "",
    }

    try:

        if _requiere_typebot(
            plantilla_maestra
        ):

            client = TypebotClient()

            typebot_info = (
                _obtener_o_clonar_typebot(
                    client=client,
                    instalacion=instalacion,
                    empresa=empresa,
                    plantilla_maestra=(
                        plantilla_maestra
                    ),
                )
            )

        typebot_id = (
            typebot_info[
                "typebot_id"
            ]
        )

        # ====================================================
        # Instalación LISTA antigua:
        # solo faltaba vincular su Typebot.
        # ====================================================

        if modo_completar_typebot:

            with transaction.atomic():

                instalacion = (
                    InstalacionPlantilla.objects
                    .select_for_update(
                        of=("self",),
                    )
                    .select_related(
                        "empresa",
                        "plantilla",
                        "plantilla_maestra",
                    )
                    .get(
                        pk=instalacion_id
                    )
                )

                if not instalacion.plantilla_id:
                    raise ValidationError(
                        (
                            "La instalación perdió su "
                            "Plantilla durante el aprovisionamiento."
                        )
                    )

                plantilla = (
                    instalacion.plantilla
                )

                bot = (
                    plantilla
                    .bots
                    .first()
                )

                if bot is None:
                    raise ValidationError(
                        (
                            "La Plantilla no tiene Bot "
                            "para asociar al Typebot."
                        )
                    )

                plantilla_externo = str(
                    plantilla.identificador_externo
                    or ""
                ).strip()

                bot_externo = str(
                    bot.identificador_externo
                    or ""
                ).strip()

                # Si otra ejecución ya terminó exactamente
                # la misma asociación, no duplicamos nada.
                if (
                    plantilla_externo
                    and bot_externo
                ):

                    if not (
                        plantilla_externo
                        == bot_externo
                        == typebot_id
                    ):
                        raise ValidationError(
                            (
                                "La asociación externa cambió "
                                "durante el aprovisionamiento."
                            )
                        )

                elif (
                    plantilla_externo
                    or bot_externo
                ):
                    raise ValidationError(
                        (
                            "La asociación externa quedó parcial "
                            "durante el aprovisionamiento."
                        )
                    )

                else:

                    plantilla.identificador_externo = (
                        typebot_id
                    )

                    plantilla.save(
                        update_fields=[
                            "identificador_externo",
                            "actualizado_en",
                        ]
                    )

                    bot.identificador_externo = (
                        typebot_id
                    )

                    bot.save(
                        update_fields=[
                            "identificador_externo",
                            "actualizado_en",
                        ]
                    )

                parametrizacion_typebot = {
                    "actualizado": False,
                    "referencias": 0,
                }

                if typebot_id:

                    if client is None:
                        raise TypebotError(
                            "Cliente Typebot no disponible."
                        )

                    parametrizacion_typebot = (
                        _parametrizar_typebot_para_bot(
                            client=client,
                            typebot_id=typebot_id,
                            bot=bot,
                            plantilla_maestra=(
                                instalacion
                                .plantilla_maestra
                            ),
                        )
                    )

                if typebot_id:

                    if client is None:
                        raise TypebotError(
                            "Cliente Typebot no disponible."
                        )

                    _asegurar_public_id_typebot(
                        client=client,
                        typebot_id=typebot_id,
                        plantilla_maestra=(
                            instalacion
                            .plantilla_maestra
                        ),
                        instalacion=instalacion,
                    )

                publicacion_typebot = {
                    "publicado": False,
                    "ya_publicado": False,
                    "publish_ejecutado": False,
                }

                if typebot_id:

                    if client is None:
                        raise TypebotError(
                            "Cliente Typebot no disponible."
                        )

                    publicacion_typebot = (
                        _publicar_typebot_si_necesario(
                            client=client,
                            typebot_id=typebot_id,
                            plantilla_maestra=(
                                instalacion
                                .plantilla_maestra
                            ),
                            forzar_publicacion=bool(
                                parametrizacion_typebot[
                                    "actualizado"
                                ]
                            ),
                        )
                    )

                canal, canal_creado = (
                    _asegurar_canal_whatsapp(
                        bot
                    )
                )

                instalacion.estado = (
                    InstalacionPlantilla
                    .Estado
                    .LISTA
                )
                instalacion.ultimo_error = ""

                instalacion.save(
                    update_fields=[
                        "estado",
                        "ultimo_error",
                        "actualizado_en",
                    ]
                )

                return {
                    "instalacion": instalacion,
                    "plantilla": plantilla,
                    "bot": bot,
                    "canal": canal,
                    "canal_creado": canal_creado,
                    "catalogo": (
                        plantilla
                        .catalogos
                        .first()
                    ),
                    "idempotente": False,
                    "typebot_id": typebot_id,
                    "typebot_creado": (
                        typebot_info[
                            "creado"
                        ]
                    ),
                    "typebot_recuperado": (
                        typebot_info[
                            "recuperado"
                        ]
                    ),
                    "typebot_publicado": (
                        publicacion_typebot[
                            "publicado"
                        ]
                    ),
                    "typebot_ya_publicado": (
                        publicacion_typebot[
                            "ya_publicado"
                        ]
                    ),
                    "typebot_publish_ejecutado": (
                        publicacion_typebot[
                            "publish_ejecutado"
                        ]
                    ),
                }

        # ====================================================
        # Instalación nueva / reintento limpio.
        # ====================================================

        with transaction.atomic():

            instalacion = (
                InstalacionPlantilla.objects
                .select_for_update()
                .select_related(
                    "empresa",
                    "plantilla_maestra",
                )
                .get(
                    pk=instalacion_id
                )
            )

            if (
                instalacion.estado
                != InstalacionPlantilla.Estado.APROVISIONANDO
            ):
                raise ValidationError(
                    (
                        "La instalación cambió de estado "
                        "antes de crear los recursos."
                    )
                )

            resultado = (
                _crear_recursos_operativos(
                    instalacion=instalacion,
                    empresa=instalacion.empresa,
                    plantilla_maestra=(
                        instalacion
                        .plantilla_maestra
                    ),
                    typebot_id=typebot_id,
                )
            )

            parametrizacion_typebot = {
                "actualizado": False,
                "referencias": 0,
            }

            if (
                typebot_id
                and resultado.get(
                    "bot"
                ) is not None
            ):

                if client is None:
                    raise TypebotError(
                        "Cliente Typebot no disponible."
                    )

                parametrizacion_typebot = (
                    _parametrizar_typebot_para_bot(
                        client=client,
                        typebot_id=typebot_id,
                        bot=resultado["bot"],
                        plantilla_maestra=(
                            instalacion
                            .plantilla_maestra
                        ),
                    )
                )

            if typebot_id:

                if client is None:
                    raise TypebotError(
                        "Cliente Typebot no disponible."
                    )

                _asegurar_public_id_typebot(
                    client=client,
                    typebot_id=typebot_id,
                    plantilla_maestra=(
                        instalacion
                        .plantilla_maestra
                    ),
                    instalacion=instalacion,
                )

            publicacion_typebot = {
                "publicado": False,
                "ya_publicado": False,
                "publish_ejecutado": False,
            }

            if typebot_id:

                if client is None:
                    raise TypebotError(
                        "Cliente Typebot no disponible."
                    )

                publicacion_typebot = (
                    _publicar_typebot_si_necesario(
                        client=client,
                        typebot_id=typebot_id,
                        plantilla_maestra=(
                            instalacion
                            .plantilla_maestra
                        ),
                        forzar_publicacion=bool(
                            parametrizacion_typebot[
                                "actualizado"
                            ]
                        ),
                    )
                )

            resultado[
                "typebot_parametrizado"
            ] = (
                parametrizacion_typebot[
                    "actualizado"
                ]
            )

            resultado[
                "typebot_bot_id_referencias"
            ] = (
                parametrizacion_typebot[
                    "referencias"
                ]
            )

            resultado[
                "idempotente"
            ] = False

            resultado[
                "typebot_id"
            ] = typebot_id

            resultado[
                "typebot_creado"
            ] = typebot_info[
                "creado"
            ]

            resultado[
                "typebot_recuperado"
            ] = typebot_info[
                "recuperado"
            ]

            resultado[
                "typebot_publicado"
            ] = publicacion_typebot[
                "publicado"
            ]

            resultado[
                "typebot_ya_publicado"
            ] = publicacion_typebot[
                "ya_publicado"
            ]

            resultado[
                "typebot_publish_ejecutado"
            ] = publicacion_typebot[
                "publish_ejecutado"
            ]

            return resultado

    except Exception as exc:

        rollback_error = ""

        # Solo archivamos automáticamente un clon que fue
        # creado EN ESTA ejecución.
        #
        # Un clon recuperado de una ejecución interrumpida
        # se conserva para poder reutilizarlo en el reintento.
        if (
            client is not None
            and typebot_info.get(
                "creado"
            )
            and typebot_info.get(
                "typebot_id"
            )
        ):

            try:
                rollback_error = (
                    _archivar_typebot_rollback(
                        client=client,
                        typebot_id=(
                            typebot_info[
                                "typebot_id"
                            ]
                        ),
                    )
                )
            except Exception as rollback_exc:
                rollback_error = (
                    "Rollback Typebot lanzó excepción: "
                    f"{_texto_error(rollback_exc)}"
                )[:1500]

        error_texto = _texto_error(
            exc
        )

        if rollback_error:
            error_texto = (
                f"{error_texto} | "
                f"{rollback_error}"
            )[:4000]

        if modo_completar_typebot:

            # La parte local ya era válida antes de esta
            # operación. Regresamos a LISTA para permitir
            # reintentar exclusivamente la integración externa.
            InstalacionPlantilla.objects.filter(
                pk=instalacion_id
            ).update(
                estado=(
                    InstalacionPlantilla
                    .Estado
                    .LISTA
                ),
                ultimo_error=error_texto,
                actualizado_en=timezone.now(),
            )

        else:

            InstalacionPlantilla.objects.filter(
                pk=instalacion_id
            ).update(
                estado=(
                    InstalacionPlantilla
                    .Estado
                    .ERROR
                ),
                ultimo_error=error_texto,
                completada_en=None,
                actualizado_en=timezone.now(),
            )

        raise

