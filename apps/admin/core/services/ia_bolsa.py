"""
Control transaccional de consumo de IA para NegocioListo.

TNL-IA-BOLSA-SERVICE-V1

Reglas comerciales:
- La bolsa base predeterminada contiene 1,000 palabras; Administración puede asignar otra cantidad por empresa.
- Sólo puede existir una bolsa activa por empresa.
- El consumo comercial corresponde a palabras de salida de IA.
- Los tokens de entrada/salida se registran para control técnico.
- Cuando el saldo llega a cero:
    * la bolsa queda agotada;
    * la configuración IA queda deshabilitada;
    * el estado pasa a pausada_agotada.
- Una nueva bolsa debe activarse explícitamente.
- Este módulo NO llama a ningún proveedor de IA.
"""

from __future__ import annotations

import re

from django.db import transaction
from django.utils import timezone

# TNL-IA-OPENAI-DEFAULT-MODEL-V1
from core.services.openai_provider import (
    OPENAI_MODEL_DEFAULT,
)

from core.models import (
    BolsaIA,
    ConfiguracionIA,
    ConsumoIA,
    Empresa,
)


# TNL-IA-BOLSA-CANTIDAD-CONFIGURABLE-V1
TAMANO_BOLSA_BASE = 1000

# Límite defensivo compatible con
# PositiveIntegerField / INTEGER en PostgreSQL.
MAX_CANTIDAD_BOLSA = 2_000_000_000


# Una "palabra comercial" es un bloque separado por
# espacios que contenga al menos un carácter alfanumérico.
#
# Ejemplos:
# "Hola, mundo" -> 2
# "- 10:00"     -> 1
# "1,000 MXN"   -> 2
#
# Esto mantiene un criterio estable y auditable sin
# depender del tokenizer particular de OpenAI.
_WORD_CHAR_RE = re.compile(
    r"\w",
    flags=re.UNICODE,
)

_NONSPACE_RE = re.compile(
    r"\S+",
    flags=re.UNICODE,
)


class IAControlError(Exception):
    """Error base del control de IA."""


class IAInactivaError(IAControlError):
    """La empresa no tiene IA disponible."""


class BolsaIAActivaError(IAControlError):
    """La empresa ya dispone de una bolsa activa."""


class BolsaIAAgotadaError(IAControlError):
    """La empresa no dispone de palabras IA."""


class SaldoIAInsuficienteError(IAControlError):

    def __init__(
        self,
        *,
        solicitadas: int,
        disponibles: int,
    ):

        self.solicitadas = solicitadas
        self.disponibles = disponibles

        super().__init__(
            "La respuesta excede el saldo "
            "disponible de palabras IA."
        )


class ConsumoIAInvalidoError(IAControlError):
    """Los datos de consumo no son válidos."""


class BolsaIACantidadInvalidaError(IAControlError):
    """La cantidad solicitada para una bolsa no es válida."""


class BolsaIASinActivaError(IAControlError):
    """La empresa no tiene una bolsa activa editable."""


def _normalizar_cantidad_bolsa(
    value,
) -> int:
    """
    Convierte y valida la cantidad comercial de una bolsa.
    """

    if isinstance(
        value,
        bool,
    ):
        raise BolsaIACantidadInvalidaError(
            "La cantidad de palabras no es válida."
        )


    text = str(
        value
        if value is not None
        else ""
    ).strip()


    # Acepta también representación administrativa
    # como 1,000.
    text = text.replace(
        ",",
        "",
    )


    try:

        cantidad = int(
            text
        )

    except (
        TypeError,
        ValueError,
    ):

        raise BolsaIACantidadInvalidaError(
            "Ingresa una cantidad entera de palabras."
        )


    if cantidad <= 0:

        raise BolsaIACantidadInvalidaError(
            "La cantidad debe ser mayor a cero."
        )


    if cantidad > MAX_CANTIDAD_BOLSA:

        raise BolsaIACantidadInvalidaError(
            "La cantidad solicitada supera "
            "el límite permitido."
        )


    return cantidad


def contar_palabras(
    texto: str,
) -> int:
    """
    Cuenta palabras comerciales de forma determinista.
    """

    if not texto:
        return 0

    total = 0

    for match in _NONSPACE_RE.finditer(
        str(texto)
    ):

        token = match.group(0)

        if _WORD_CHAR_RE.search(
            token
        ):

            total += 1

    return total


def limitar_texto_a_palabras(
    texto: str,
    max_palabras: int,
) -> str:
    """
    Devuelve como máximo max_palabras palabras.

    Conserva el texto original hasta el final de
    la última palabra permitida.
    """

    if max_palabras < 0:
        raise ValueError(
            "max_palabras no puede ser negativo."
        )

    if not texto or max_palabras == 0:
        return ""

    encontradas = 0
    corte = None

    for match in _NONSPACE_RE.finditer(
        str(texto)
    ):

        token = match.group(0)

        if not _WORD_CHAR_RE.search(
            token
        ):
            continue

        encontradas += 1
        corte = match.end()

        if encontradas >= max_palabras:
            break

    if corte is None:
        return ""

    if encontradas < max_palabras:
        return str(texto).strip()

    return str(texto)[:corte].rstrip()


def obtener_estado_ia(
    empresa_id: int,
) -> dict:
    """
    Lectura del estado comercial de IA.

    TNL-IA-ESTADO-ULTIMA-BOLSA-V1

    Mantiene visible la última bolsa aunque ya esté
    agotada, pero sólo autoriza IA si existe una
    bolsa ACTIVA con saldo.
    """

    config = (
        ConfiguracionIA.objects
        .filter(
            empresa_id=empresa_id
        )
        .first()
    )

    if config is None:

        return {
            "configurada": False,
            "habilitada": False,
            "estado": "sin_configuracion",
            "proveedor": "",
            "modelo": "",
            "bolsa_activa_id": None,
            "bolsa_actual_id": None,
            "bolsa_estado": "",
            "cantidad_palabras": 0,
            "palabras_consumidas": 0,
            "palabras_disponibles": 0,
            "puede_usar_ia": False,
        }


    bolsa_activa = (
        BolsaIA.objects
        .filter(
            empresa_id=empresa_id,
            estado=BolsaIA.ESTADO_ACTIVA,
        )
        .order_by(
            "-id"
        )
        .first()
    )


    bolsa_actual = (
        bolsa_activa
        or
        BolsaIA.objects
        .filter(
            empresa_id=empresa_id
        )
        .order_by(
            "-id"
        )
        .first()
    )


    disponibles = (
        bolsa_actual.palabras_disponibles
        if bolsa_actual is not None
        else 0
    )


    puede_usar = bool(
        config.habilitada
        and
        config.estado
        ==
        ConfiguracionIA.ESTADO_ACTIVA
        and
        bolsa_activa is not None
        and
        bolsa_activa.palabras_disponibles > 0
    )


    return {
        "configurada": True,
        "habilitada": config.habilitada,
        "estado": config.estado,
        "proveedor": config.proveedor,
        "modelo": config.modelo,

        "bolsa_activa_id":
            bolsa_activa.id
            if bolsa_activa is not None
            else None,

        "bolsa_actual_id":
            bolsa_actual.id
            if bolsa_actual is not None
            else None,

        "bolsa_estado":
            bolsa_actual.estado
            if bolsa_actual is not None
            else "",

        "cantidad_palabras":
            bolsa_actual.cantidad_palabras
            if bolsa_actual is not None
            else 0,

        "palabras_consumidas":
            bolsa_actual.palabras_consumidas
            if bolsa_actual is not None
            else 0,

        "palabras_disponibles":
            disponibles,

        "puede_usar_ia":
            puede_usar,
    }


def validar_disponibilidad_ia(
    empresa_id: int,
) -> dict:
    """
    Pre-check sin escritura antes de llamar al proveedor.

    La operación de registro vuelve a validar todo
    bajo bloqueo transaccional y es la autoridad final.
    """

    estado = obtener_estado_ia(
        empresa_id
    )


    if not estado[
        "configurada"
    ]:

        raise IAInactivaError(
            "IA no configurada para la empresa."
        )


    if not estado[
        "habilitada"
    ]:

        if (
            estado["estado"]
            ==
            ConfiguracionIA
            .ESTADO_PAUSADA_AGOTADA
        ):

            raise BolsaIAAgotadaError(
                "Bolsa IA agotada."
            )

        raise IAInactivaError(
            "IA deshabilitada para la empresa."
        )


    if not estado[
        "puede_usar_ia"
    ]:

        raise BolsaIAAgotadaError(
            "No hay una bolsa IA "
            "activa con saldo."
        )


    return estado


@transaction.atomic
def activar_nueva_bolsa(
    *,
    empresa_id: int,
    cantidad_palabras: int = TAMANO_BOLSA_BASE,
    notas: str = "",
) -> BolsaIA:
    """
    Activa manualmente una nueva bolsa.

    La cantidad predeterminada continúa siendo
    TAMANO_BOLSA_BASE, pero Administración puede
    asignar otra cantidad por empresa.
    """

    cantidad_palabras = (
        _normalizar_cantidad_bolsa(
            cantidad_palabras
        )
    )


    empresa = (
        Empresa.objects
        .select_for_update()
        .get(
            pk=empresa_id
        )
    )


    bolsa_activa = (
        BolsaIA.objects
        .select_for_update()
        .filter(
            empresa=empresa,
            estado=BolsaIA.ESTADO_ACTIVA,
        )
        .order_by(
            "-id"
        )
        .first()
    )


    if bolsa_activa is not None:

        if (
            bolsa_activa
            .palabras_disponibles
            > 0
        ):

            raise BolsaIAActivaError(
                "La empresa ya tiene "
                "una bolsa IA activa."
            )


        bolsa_activa.estado = (
            BolsaIA.ESTADO_AGOTADA
        )

        if (
            bolsa_activa.agotada_en
            is None
        ):

            bolsa_activa.agotada_en = (
                timezone.now()
            )


        bolsa_activa.save(
            update_fields=[
                "estado",
                "agotada_en",
                "actualizado_en",
            ]
        )


    config, _ = (
        ConfiguracionIA.objects
        .select_for_update()
        .get_or_create(
            empresa=empresa,
            defaults={
                "proveedor":
                    ConfiguracionIA
                    .PROVEEDOR_OPENAI,

                "modelo":
                    OPENAI_MODEL_DEFAULT,

                "habilitada":
                    False,

                "estado":
                    ConfiguracionIA
                    .ESTADO_INACTIVA,
            },
        )
    )


    nueva_bolsa = (
        BolsaIA.objects.create(
            empresa=empresa,
            cantidad_palabras=
                cantidad_palabras,
            palabras_consumidas=0,
            estado=
                BolsaIA.ESTADO_ACTIVA,
            notas=notas or "",
        )
    )


    config.habilitada = True

    config.estado = (
        ConfiguracionIA.ESTADO_ACTIVA
    )

    config.ultimo_error = ""

    config.save(
        update_fields=[
            "habilitada",
            "estado",
            "ultimo_error",
            "actualizado_en",
        ]
    )


    return nueva_bolsa



@transaction.atomic
def actualizar_bolsa_activa(
    *,
    empresa_id: int,
    cantidad_palabras: int,
) -> BolsaIA:
    """
    Modifica únicamente el límite comercial de
    la bolsa ACTIVA de una empresa.

    Nunca modifica palabras_consumidas ni
    registros ConsumoIA.

    Si la nueva cantidad queda exactamente igual
    a las palabras ya consumidas, la bolsa se
    considera agotada y la IA se pausa.
    """

    cantidad_palabras = (
        _normalizar_cantidad_bolsa(
            cantidad_palabras
        )
    )


    empresa = (
        Empresa.objects
        .select_for_update()
        .get(
            pk=empresa_id
        )
    )


    bolsa = (
        BolsaIA.objects
        .select_for_update()
        .filter(
            empresa=empresa,
            estado=BolsaIA.ESTADO_ACTIVA,
        )
        .order_by(
            "-id"
        )
        .first()
    )


    if bolsa is None:

        raise BolsaIASinActivaError(
            "La empresa no tiene una "
            "bolsa IA activa para editar."
        )


    consumidas = int(
        bolsa.palabras_consumidas
    )


    if (
        cantidad_palabras
        <
        consumidas
    ):

        raise BolsaIACantidadInvalidaError(
            "La cantidad no puede ser menor "
            "a las palabras ya consumidas "
            f"({consumidas:,})."
        )


    anterior = int(
        bolsa.cantidad_palabras
    )


    if (
        cantidad_palabras
        ==
        anterior
    ):

        return bolsa


    bolsa.cantidad_palabras = (
        cantidad_palabras
    )


    nota_ajuste = (
        "Ajuste administrativo de bolsa: "
        f"{anterior:,} -> "
        f"{cantidad_palabras:,} palabras."
    )


    notas_actuales = str(
        bolsa.notas
        or ""
    ).strip()


    bolsa.notas = (
        (
            notas_actuales
            +
            "\n"
            +
            nota_ajuste
        ).strip()
        if notas_actuales
        else nota_ajuste
    )


    agotada = bool(
        cantidad_palabras
        ==
        consumidas
    )


    update_fields = [
        "cantidad_palabras",
        "notas",
        "actualizado_en",
    ]


    if agotada:

        bolsa.estado = (
            BolsaIA.ESTADO_AGOTADA
        )

        bolsa.agotada_en = (
            timezone.now()
        )

        update_fields.extend(
            [
                "estado",
                "agotada_en",
            ]
        )


    elif bolsa.agotada_en is not None:

        bolsa.agotada_en = None

        update_fields.append(
            "agotada_en"
        )


    bolsa.save(
        update_fields=
            update_fields
    )


    if agotada:

        config = (
            ConfiguracionIA.objects
            .select_for_update()
            .filter(
                empresa=empresa
            )
            .first()
        )


        if config is not None:

            config.habilitada = False

            config.estado = (
                ConfiguracionIA
                .ESTADO_PAUSADA_AGOTADA
            )

            config.save(
                update_fields=[
                    "habilitada",
                    "estado",
                    "actualizado_en",
                ]
            )


    return bolsa


@transaction.atomic
def registrar_consumo_respuesta(
    *,
    empresa_id: int,
    texto_salida: str,
    tokens_entrada: int = 0,
    tokens_salida: int = 0,
    modelo: str = "",
    referencia_conversacion: str = "",
    origen: str = "",
) -> ConsumoIA:
    """
    Registra una respuesta ya generada.

    IMPORTANTE:
    esta función vuelve a validar el saldo bajo
    SELECT ... FOR UPDATE antes de descontar.

    Si la respuesta supera el saldo actual,
    no registra consumo y lanza
    SaldoIAInsuficienteError.
    """

    if tokens_entrada < 0:
        raise ConsumoIAInvalidoError(
            "tokens_entrada no puede ser negativo."
        )


    if tokens_salida < 0:
        raise ConsumoIAInvalidoError(
            "tokens_salida no puede ser negativo."
        )


    palabras = contar_palabras(
        texto_salida
    )


    if palabras <= 0:

        raise ConsumoIAInvalidoError(
            "La respuesta no contiene "
            "palabras contabilizables."
        )


    empresa = (
        Empresa.objects
        .select_for_update()
        .get(
            pk=empresa_id
        )
    )


    try:

        config = (
            ConfiguracionIA.objects
            .select_for_update()
            .get(
                empresa=empresa
            )
        )

    except ConfiguracionIA.DoesNotExist:

        raise IAInactivaError(
            "IA no configurada para la empresa."
        )


    if not config.habilitada:

        if (
            config.estado
            ==
            ConfiguracionIA
            .ESTADO_PAUSADA_AGOTADA
        ):

            raise BolsaIAAgotadaError(
                "Bolsa IA agotada."
            )

        raise IAInactivaError(
            "IA deshabilitada para la empresa."
        )


    if (
        config.estado
        !=
        ConfiguracionIA.ESTADO_ACTIVA
    ):

        raise IAInactivaError(
            "IA no se encuentra activa."
        )


    bolsa = (
        BolsaIA.objects
        .select_for_update()
        .filter(
            empresa=empresa,
            estado=BolsaIA.ESTADO_ACTIVA,
        )
        .order_by(
            "-id"
        )
        .first()
    )


    if bolsa is None:

        raise BolsaIAAgotadaError(
            "No existe una bolsa IA activa."
        )


    disponibles = (
        bolsa.palabras_disponibles
    )


    if disponibles <= 0:

        bolsa.estado = (
            BolsaIA.ESTADO_AGOTADA
        )

        if bolsa.agotada_en is None:

            bolsa.agotada_en = (
                timezone.now()
            )


        bolsa.save(
            update_fields=[
                "estado",
                "agotada_en",
                "actualizado_en",
            ]
        )


        config.habilitada = False

        config.estado = (
            ConfiguracionIA
            .ESTADO_PAUSADA_AGOTADA
        )

        config.save(
            update_fields=[
                "habilitada",
                "estado",
                "actualizado_en",
            ]
        )


        raise BolsaIAAgotadaError(
            "Bolsa IA agotada."
        )


    if palabras > disponibles:

        raise SaldoIAInsuficienteError(
            solicitadas=palabras,
            disponibles=disponibles,
        )


    nuevo_consumo = (
        bolsa.palabras_consumidas
        +
        palabras
    )


    bolsa.palabras_consumidas = (
        nuevo_consumo
    )


    agotada = bool(
        nuevo_consumo
        >=
        bolsa.cantidad_palabras
    )


    ahora = timezone.now()


    if agotada:

        bolsa.estado = (
            BolsaIA.ESTADO_AGOTADA
        )

        bolsa.agotada_en = ahora


    bolsa_fields = [
        "palabras_consumidas",
        "actualizado_en",
    ]


    if agotada:

        bolsa_fields.extend(
            [
                "estado",
                "agotada_en",
            ]
        )


    bolsa.save(
        update_fields=
            bolsa_fields
    )


    consumo = (
        ConsumoIA.objects.create(
            empresa=empresa,
            bolsa=bolsa,
            proveedor=config.proveedor,
            modelo=(
                modelo
                or
                config.modelo
                or
                ""
            ),
            palabras_salida=palabras,
            tokens_entrada=
                tokens_entrada,
            tokens_salida=
                tokens_salida,
            referencia_conversacion=
                referencia_conversacion
                or "",
            origen=
                origen
                or "",
        )
    )


    config.ultima_actividad_en = (
        ahora
    )


    config_fields = [
        "ultima_actividad_en",
        "actualizado_en",
    ]


    if agotada:

        config.habilitada = False

        config.estado = (
            ConfiguracionIA
            .ESTADO_PAUSADA_AGOTADA
        )

        config_fields.extend(
            [
                "habilitada",
                "estado",
            ]
        )


    config.save(
        update_fields=
            config_fields
    )


    return consumo
