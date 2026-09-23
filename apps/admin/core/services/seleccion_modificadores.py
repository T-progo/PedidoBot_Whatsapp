"""
Resolución de una selección de modificadores escrita a mano.

TNL-MODIFICADOR-TEXTO-V1

Cuando el cliente escribe en lugar de tocar la lista ("1",
"BBQ", "1 y 9"), esta capa traduce ese texto a IDs reales de
opción del grupo ACTUAL. Es la única autoridad: nunca acepta
precios del cliente, no inventa opciones y no deja pasar una
selección que rompa las reglas del grupo.

Si algo es inválido o ambiguo no se adivina: se devuelve un
mensaje corto para que el cliente elija otra vez.
"""

from __future__ import annotations

import re
import unicodedata


SEPARADORES = re.compile(
    r"[,;/|+]|\by\b|\be\b|\bmas\b|\band\b|\s+"
)

RUIDO = re.compile(r"^[\s.\-)(]+|[\s.\-)(]+$")


def normalizar(texto) -> str:
    """Minúsculas, sin acentos y sin espacios repetidos."""

    crudo = str(texto if texto is not None else "")

    sin_acentos = "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", crudo)
        if not unicodedata.combining(caracter)
    )

    return " ".join(sin_acentos.casefold().split())


def _nombre_de_etiqueta(etiqueta) -> str:
    """
    "2. Buffalo hot (+5.00)" -> "buffalo hot".
    La etiqueta que ve el cliente lleva índice y precio; para
    comparar sólo interesa el nombre.
    """

    texto = normalizar(etiqueta)
    texto = re.sub(r"^\d+\s*[.)-]\s*", "", texto)
    texto = re.sub(r"\(\s*\+?[\d.,]+\s*\)\s*$", "", texto)

    return texto.strip()


def _trozos(texto: str) -> list[str]:
    """Parte el mensaje en candidatos, sin perder nombres compuestos."""

    normalizado = normalizar(texto)

    if not normalizado:
        return []

    # Si el mensaje es sólo números y separadores, cada número
    # es una selección ("1 y 9", "1, 9", "1 9").
    if re.fullmatch(r"[\d\s,;/|+.\-]*\d[\d\s,;/|+.\-]*", normalizado):
        return [t for t in re.findall(r"\d+", normalizado)]

    # Con texto, sólo separadores explícitos: un nombre puede
    # llevar espacios ("buffalo hot").
    partes = re.split(r"[,;/|]|\s+y\s+|\s+e\s+|\s+mas\s+", normalizado)

    return [RUIDO.sub("", parte) for parte in partes if RUIDO.sub("", parte)]


def _candidatos_por_nombre(trozo, nombres, etiquetas) -> list[int]:
    """Índices (base 0) de las opciones que coinciden con el texto."""

    exactos = [
        indice
        for indice, nombre in enumerate(nombres)
        if normalizar(nombre) == trozo
        or _nombre_de_etiqueta(etiquetas[indice]) == trozo
    ]

    if exactos:
        return exactos

    return [
        indice
        for indice, nombre in enumerate(nombres)
        if trozo and (
            normalizar(nombre).startswith(trozo)
            or _nombre_de_etiqueta(etiquetas[indice]).startswith(trozo)
        )
    ]


def resolver_texto_opciones(
    *,
    texto,
    opcion_ids,
    opcion_nombres,
    opcion_etiquetas=None,
    maximo=0,
    seleccionadas=None,
) -> dict:
    """
    Traduce el texto del cliente a IDs del grupo actual.

    Devuelve siempre un dict con:
      resuelto   -> bool
      opcion_ids -> IDs nuevos (vacío si no se resolvió)
      acumuladas -> selección completa ya validada
      mensaje    -> texto corto para el cliente
      motivo     -> etiqueta técnica del rechazo
    """

    ids = [int(valor) for valor in (opcion_ids or [])]
    nombres = [str(valor) for valor in (opcion_nombres or [])]
    etiquetas = [str(valor) for valor in (opcion_etiquetas or [])]

    while len(etiquetas) < len(ids):
        etiquetas.append("")

    previas = []

    for valor in (seleccionadas or []):
        try:
            numero = int(valor)
        except (TypeError, ValueError):
            continue
        if numero not in previas:
            previas.append(numero)

    def fallo(motivo, mensaje):
        return {
            "resuelto": False,
            "opcion_ids": [],
            "acumuladas": previas,
            "mensaje": mensaje,
            "motivo": motivo,
        }

    if not ids or len(nombres) != len(ids):
        return fallo(
            "sin_opciones",
            "Ahora mismo no hay opciones disponibles para este grupo.",
        )

    trozos = _trozos(texto)

    if not trozos:
        return fallo(
            "vacio",
            "Elige una opción de la lista escribiendo su número o su nombre.",
        )

    maximo = int(maximo or 0)

    if maximo == 1 and len(trozos) > 1:
        return fallo(
            "solo_una",
            "En este paso sólo puedes elegir una opción.",
        )

    elegidos: list[int] = []

    for trozo in trozos:

        if trozo.isdigit():

            indice = int(trozo) - 1

            if indice < 0 or indice >= len(ids):
                return fallo(
                    "numero_invalido",
                    f"El número {trozo} no está en la lista. "
                    f"Elige entre 1 y {len(ids)}.",
                )

        else:

            candidatos = _candidatos_por_nombre(trozo, nombres, etiquetas)

            if not candidatos:
                return fallo(
                    "nombre_invalido",
                    "No encontramos esa opción. Escribe su número "
                    "o su nombre tal como aparece en la lista.",
                )

            if len(candidatos) > 1:
                return fallo(
                    "ambiguo",
                    "Esa opción puede ser varias de la lista. "
                    "Escribe su número para no equivocarnos.",
                )

            indice = candidatos[0]

        opcion_id = ids[indice]

        if opcion_id in elegidos:
            return fallo(
                "repetida_en_mensaje",
                f"Repetiste «{nombres[indice]}». Escribe cada "
                "opción una sola vez.",
            )

        if opcion_id in previas:
            return fallo(
                "ya_elegida",
                f"Ya habías agregado «{nombres[indice]}». "
                "Elige otra de la lista.",
            )

        elegidos.append(opcion_id)

    if maximo > 0:

        ya_en_grupo = len([
            valor
            for valor in previas
            if valor in ids
        ])

        if ya_en_grupo + len(elegidos) > maximo:
            return fallo(
                "maximo",
                f"En este grupo puedes elegir máximo {maximo} "
                "opción(es).",
            )

    return {
        "resuelto": True,
        "opcion_ids": elegidos,
        "acumuladas": previas + elegidos,
        "mensaje": "",
        "motivo": "",
    }
