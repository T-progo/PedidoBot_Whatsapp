"""
Representación legible de las líneas de un pedido.

TNL-LINEAS-PEDIDO-V1

Se arma sólo con lo que ya quedó guardado en la línea
(nombre, cantidad, importe y los snapshots de modificadores y
extras). Nunca recalcula precios ni interpreta el texto que se
muestra al cliente: los importes vienen tal cual del pedido.

La misma descripción sirve para el resumen del cliente, la
consulta de pedido y, más adelante, el ticket de cocina.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


SANGRIA = "   "


def _texto(valor) -> str:
    """Texto de una sola línea, sin espacios repetidos."""

    return " ".join(str(valor if valor is not None else "").split())


def cantidad_legible(valor) -> str:
    """
    2 en lugar de 2.0000; conserva los decimales cuando los
    hay y devuelve el texto original si no es un número.
    """

    texto = _texto(valor)

    if not texto:
        return "0"

    try:
        numero = Decimal(texto)
    except (InvalidOperation, ValueError):
        return texto

    if numero == numero.to_integral_value():
        return str(int(numero))

    return format(numero.normalize(), "f")


def importe_legible(valor) -> str:
    """
    40.0000 se muestra como 40.00. Si hay fracciones de
    centavo reales el valor se deja intacto: preferimos que un
    dato raro se vea a que quede escondido por un redondeo.
    """

    texto = _texto(valor)

    if not texto:
        return "0.00"

    try:
        numero = Decimal(texto)
    except (InvalidOperation, ValueError):
        return texto

    centavos = numero.quantize(Decimal("0.01"))

    if centavos != numero:
        return texto

    return format(centavos, "f")


def _opciones_de_grupo(grupo) -> list[dict]:
    """Opciones legibles de un grupo del snapshot."""

    opciones = []

    for opcion in (grupo.get("opciones") or []):

        if not isinstance(opcion, dict):
            continue

        nombre = _texto(opcion.get("nombre"))

        if not nombre:
            continue

        opciones.append(
            {
                "opcion_id": opcion.get("opcion_id"),
                "nombre": nombre,
                "precio_adicional": _texto(
                    opcion.get("precio_adicional")
                ),
            }
        )

    return opciones


def grupos_de_snapshots(*snapshots) -> list[dict]:
    """
    Grupos con opciones a partir de los snapshots guardados.
    Tolera datos incompletos: nunca lanza excepción, porque un
    snapshot viejo no debe romper el resumen de un pedido.
    """

    grupos = []

    for snapshot in snapshots:

        for grupo in (snapshot or []):

            if not isinstance(grupo, dict):
                continue

            opciones = _opciones_de_grupo(grupo)

            if not opciones:
                continue

            grupos.append(
                {
                    "tipo": _texto(grupo.get("tipo")),
                    "grupo_id": grupo.get("grupo_id"),
                    "nombre": (
                        _texto(grupo.get("grupo_nombre"))
                        or "Opciones"
                    ),
                    "opciones": opciones,
                }
            )

    return grupos


def describir_linea(
    *,
    nombre,
    cantidad,
    importe,
    modificadores=None,
    extras=None,
) -> dict:
    """Descripción estructurada de una línea ya guardada."""

    return {
        "nombre": _texto(nombre) or "Producto",
        "cantidad": cantidad_legible(cantidad),
        "importe": importe_legible(importe),
        "grupos": grupos_de_snapshots(modificadores, extras),
    }


def describir_detalle(detalle) -> dict:
    """Descripción estructurada de un PedidoDetalle."""

    return describir_linea(
        nombre=detalle.nombre_producto,
        cantidad=detalle.cantidad,
        importe=detalle.importe,
        modificadores=detalle.modificadores_snapshot,
        extras=detalle.extras_snapshot,
    )


def texto_linea(
    descripcion,
    *,
    prefijo="",
    sangria=SANGRIA,
    con_importe=True,
) -> str:
    """
    Una línea y sus opciones:

        1. Alitas x2 — $30.00
           Salsa: BBQ
           Extras: Buffalo hot, Teriyaki
    """

    encabezado = (
        f"{prefijo}{descripcion['nombre']} "
        f"x{descripcion['cantidad']}"
    )

    if con_importe:
        encabezado += f" — ${descripcion['importe']}"

    filas = [encabezado]

    for grupo in descripcion["grupos"]:

        opciones = ", ".join(
            opcion["nombre"] for opcion in grupo["opciones"]
        )

        filas.append(f"{sangria}{grupo['nombre']}: {opciones}")

    return "\n".join(filas)


def texto_lineas(
    descripciones,
    *,
    numerar=True,
    vineta="• ",
    sangria=SANGRIA,
    con_importe=True,
) -> str:
    """Varias líneas, numeradas o con viñeta."""

    filas = []

    for indice, descripcion in enumerate(descripciones, start=1):

        prefijo = f"{indice}. " if numerar else vineta

        filas.append(
            texto_linea(
                descripcion,
                prefijo=prefijo,
                sangria=sangria,
                con_importe=con_importe,
            )
        )

    return "\n".join(filas)
