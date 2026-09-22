"""
Reglas compartidas del catálogo.

TNL-CATALOGO-REGLAS-V1

- Precisión de precios: máximo 2 decimales (centavos).
- Producto vendible: una sola definición para el menú del
  restaurante, el detalle, el carrito, la confirmación y el
  catálogo de la IA.

TNL-RESTAURANTE-DISPONIBILIDAD-V1
Los restaurantes no usan inventario numérico: un producto
está Disponible (activo) o Agotado (inactivo), y una opción
de modificador está disponible si está activa.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db.models import Count, Exists, F, OuterRef, Q


DECIMALES_PRECIO = 2

MENSAJE_PRECIO_CENTAVOS = (
    "El precio admite máximo 2 decimales (centavos)."
)


def precio_en_centavos(valor) -> bool:
    """
    True si el valor es un número finito sin fracciones
    de centavo (12, 12.5, 12.50 o 12.5000 son válidos;
    12.345 no). No redondea ni corrige.
    """

    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return False

    if not numero.is_finite():
        return False

    return numero == numero.quantize(Decimal("0.01"))


def es_bot_restaurante(bot) -> bool:

    plantilla = getattr(bot, "plantilla", None)

    return str(
        getattr(plantilla, "tipo", "") or ""
    ).strip().casefold() == "restaurante"


def _grupos_obligatorios_sin_opciones_suficientes():
    """
    Grupos obligatorios activos del producto (OuterRef) que ya
    no tienen suficientes opciones disponibles para cumplir su
    mínimo: el platillo no se puede armar, está agotado.
    """

    from core.models import GrupoModificadorProducto

    return (
        GrupoModificadorProducto.objects
        .filter(
            producto_id=OuterRef("pk"),
            activo=True,
            obligatorio=True,
        )
        .annotate(
            opciones_disponibles=Count(
                "opciones",
                filter=Q(opciones__activa=True),
            ),
        )
        .filter(
            opciones_disponibles__lt=F("minimo"),
        )
    )


def filtro_producto_vendible(*, restaurante: bool) -> Q:
    """
    Condiciones para que un producto se pueda vender ahora.

    Siempre: producto activo, catálogo activo y, si tiene
    categoría, que esté activa.

    Restaurante (Disponible / Agotado, sin inventario
    numérico): además categoría obligatoria, activa y del
    mismo catálogo, y que sus grupos obligatorios tengan
    opciones disponibles. El stock numérico no cuenta.
    """

    if restaurante:
        # Sin OR: la categoría queda en INNER JOIN y el
        # filtro se puede combinar con select_for_update().
        return Q(
            Q(
                activo=True,
                catalogo__activo=True,
                categoria__isnull=False,
                categoria__activa=True,
                categoria__catalogo_id=F("catalogo_id"),
            ),
            ~Exists(
                _grupos_obligatorios_sin_opciones_suficientes()
            ),
        )

    return Q(
        activo=True,
        catalogo__activo=True,
    ) & (
        Q(categoria__isnull=True)
        | Q(categoria__activa=True)
    )


def productos_vendibles(
    *,
    empresa_id,
    plantilla_id=None,
    restaurante: bool,
    queryset=None,
):
    """
    Productos vendibles de una empresa. Con plantilla_id,
    sólo los del catálogo de esa plantilla (como el menú del
    bot). `queryset` permite conservar select_related,
    prefetch o select_for_update del llamador.
    """

    from core.models import Producto

    productos = (
        queryset
        if queryset is not None
        else Producto.objects.all()
    ).filter(
        filtro_producto_vendible(restaurante=restaurante),
        catalogo__empresa_id=empresa_id,
    )

    if plantilla_id is not None:
        productos = productos.filter(
            catalogo__plantilla_id=plantilla_id,
        )

    return productos
