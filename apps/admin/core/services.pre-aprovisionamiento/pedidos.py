from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

from django.core.exceptions import ValidationError
from django.db import transaction

from core.models import (
    Empresa,
    Canal,
    Pedido,
    PedidoDetalle,
    Producto,
)


CUATRO_DECIMALES = Decimal("0.0001")
CERO = Decimal("0.0000")


def decimal_4(valor):
    """
    Convierte y normaliza valores Decimal a exactamente 4 decimales.
    """

    try:
        return Decimal(str(valor)).quantize(
            CUATRO_DECIMALES,
            rounding=ROUND_HALF_UP,
        )
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(
            "El valor numérico proporcionado no es válido."
        )


def _generar_numero_pedido_bajo_bloqueo(empresa_id):
    """
    Debe ejecutarse dentro de transaction.atomic().

    Bloqueamos la empresa para serializar la generación del
    consecutivo por tenant.
    """

    empresa = (
        Empresa.objects
        .select_for_update()
        .get(pk=empresa_id)
    )

    ultimo_numero = (
        Pedido.objects
        .filter(
            empresa_id=empresa.id,
            numero__regex=r"^PED-[0-9]+$",
        )
        .order_by("-id")
        .values_list("numero", flat=True)
        .first()
    )

    consecutivo = 1

    if ultimo_numero:

        coincidencia = re.fullmatch(
            r"PED-([0-9]+)",
            ultimo_numero,
        )

        if coincidencia:
            consecutivo = int(
                coincidencia.group(1)
            ) + 1

    numero = f"PED-{consecutivo:06d}"

    return empresa, numero


@transaction.atomic
def crear_pedido(
    *,
    empresa_id,
    moneda,
    canal_id=None,
    cliente_nombre="",
    cliente_telefono="",
    cliente_email="",
    direccion_entrega="",
    notas="",
    identificador_externo="",
):
    """
    Crea un carrito/pedido con numeración consecutiva por empresa.
    """

    moneda = str(moneda).strip().upper()

    if len(moneda) != 3:
        raise ValidationError(
            "La moneda debe utilizar un código de 3 caracteres."
        )

    empresa, numero = (
        _generar_numero_pedido_bajo_bloqueo(
            empresa_id
        )
    )

    canal = None

    if canal_id is not None:

        canal = (
            Canal.objects
            .select_related(
                "bot",
                "bot__empresa",
            )
            .get(pk=canal_id)
        )

        if canal.bot.empresa_id != empresa.id:
            raise ValidationError(
                "El canal seleccionado no pertenece a la empresa del pedido."
            )

        if not canal.activo:
            raise ValidationError(
                "El canal seleccionado está inactivo."
            )

    pedido = Pedido(
        empresa=empresa,
        canal=canal,
        numero=numero,
        estado="carrito",
        cliente_nombre=cliente_nombre.strip(),
        cliente_telefono=cliente_telefono.strip(),
        cliente_email=cliente_email.strip(),
        direccion_entrega=direccion_entrega.strip(),
        notas=notas.strip(),
        moneda=moneda,
        subtotal=CERO,
        descuento=CERO,
        total=CERO,
        identificador_externo=identificador_externo.strip(),
    )

    pedido.save()

    return pedido


def _recalcular_pedido_bajo_bloqueo(pedido):
    """
    Recalcula todas las líneas y posteriormente el encabezado.

    subtotal  = suma cantidad * precio_unitario
    descuento = suma descuentos de línea
    total     = subtotal - descuento
    """

    detalles = (
        PedidoDetalle.objects
        .select_for_update()
        .filter(pedido_id=pedido.id)
        .order_by("id")
    )

    subtotal = CERO
    descuento_total = CERO
    total = CERO

    for detalle in detalles:

        cantidad = decimal_4(
            detalle.cantidad
        )

        precio = decimal_4(
            detalle.precio_unitario
        )

        descuento = decimal_4(
            detalle.descuento
        )

        bruto = decimal_4(
            cantidad * precio
        )

        if descuento > bruto:
            raise ValidationError(
                f"El descuento de la línea {detalle.id} "
                "no puede ser mayor que su importe bruto."
            )

        importe = decimal_4(
            bruto - descuento
        )

        if detalle.importe != importe:
            detalle.importe = importe

            detalle.save(
                update_fields=[
                    "importe",
                ]
            )

        subtotal += bruto
        descuento_total += descuento
        total += importe

    pedido.subtotal = decimal_4(
        subtotal
    )

    pedido.descuento = decimal_4(
        descuento_total
    )

    pedido.total = decimal_4(
        total
    )

    pedido.save(
        update_fields=[
            "subtotal",
            "descuento",
            "total",
            "actualizado_en",
        ]
    )

    return pedido


@transaction.atomic
def recalcular_pedido(pedido_id):
    """
    API pública para recalcular un pedido.
    """

    pedido = (
        Pedido.objects
        .select_for_update()
        .get(pk=pedido_id)
    )

    return _recalcular_pedido_bajo_bloqueo(
        pedido
    )


@transaction.atomic
def agregar_producto_a_pedido(
    *,
    pedido_id,
    producto_id,
    cantidad,
    descuento=CERO,
):
    """
    Agrega un producto al carrito usando snapshots históricos.

    No modifica inventario.
    """

    pedido = (
        Pedido.objects
        .select_for_update()
        .select_related("empresa")
        .get(pk=pedido_id)
    )

    if pedido.estado != "carrito":
        raise ValidationError(
            "Solo se pueden agregar productos a un pedido en estado Carrito."
        )

    producto = (
        Producto.objects
        .select_for_update()
        .select_related(
            "catalogo",
            "catalogo__empresa",
        )
        .get(pk=producto_id)
    )

    if not producto.activo:
        raise ValidationError(
            "El producto seleccionado está inactivo."
        )

    if not producto.catalogo.activo:
        raise ValidationError(
            "El catálogo del producto está inactivo."
        )

    if producto.catalogo.empresa_id != pedido.empresa_id:
        raise ValidationError(
            "El producto no pertenece a la empresa del pedido."
        )

    if producto.catalogo.moneda != pedido.moneda:
        raise ValidationError(
            "La moneda del producto no coincide con la moneda del pedido."
        )

    cantidad = decimal_4(
        cantidad
    )

    descuento = decimal_4(
        descuento
    )

    precio_unitario = decimal_4(
        producto.precio
    )

    if cantidad <= CERO:
        raise ValidationError(
            "La cantidad debe ser mayor que cero."
        )

    if descuento < CERO:
        raise ValidationError(
            "El descuento no puede ser negativo."
        )

    bruto = decimal_4(
        cantidad * precio_unitario
    )

    if descuento > bruto:
        raise ValidationError(
            "El descuento no puede ser mayor que el importe bruto de la línea."
        )

    importe = decimal_4(
        bruto - descuento
    )

    detalle = PedidoDetalle.objects.create(
        pedido=pedido,
        producto=producto,

        # SNAPSHOT HISTORICO
        sku=producto.sku,
        nombre_producto=producto.nombre,
        cantidad=cantidad,
        precio_unitario=precio_unitario,
        descuento=descuento,
        importe=importe,
    )

    _recalcular_pedido_bajo_bloqueo(
        pedido
    )

    detalle.refresh_from_db()

    return detalle


@transaction.atomic
def actualizar_detalle_pedido(
    *,
    detalle_id,
    cantidad,
    descuento=CERO,
):
    """
    Modifica cantidad/descuento conservando el precio histórico.
    """

    detalle = (
        PedidoDetalle.objects
        .select_for_update()
        .select_related("pedido")
        .get(pk=detalle_id)
    )

    pedido = (
        Pedido.objects
        .select_for_update()
        .get(pk=detalle.pedido_id)
    )

    if pedido.estado != "carrito":
        raise ValidationError(
            "Solo se pueden editar líneas de un pedido en estado Carrito."
        )

    cantidad = decimal_4(
        cantidad
    )

    descuento = decimal_4(
        descuento
    )

    if cantidad <= CERO:
        raise ValidationError(
            "La cantidad debe ser mayor que cero."
        )

    if descuento < CERO:
        raise ValidationError(
            "El descuento no puede ser negativo."
        )

    bruto = decimal_4(
        cantidad * detalle.precio_unitario
    )

    if descuento > bruto:
        raise ValidationError(
            "El descuento no puede ser mayor que el importe bruto de la línea."
        )

    detalle.cantidad = cantidad
    detalle.descuento = descuento
    detalle.importe = decimal_4(
        bruto - descuento
    )

    detalle.save(
        update_fields=[
            "cantidad",
            "descuento",
            "importe",
        ]
    )

    _recalcular_pedido_bajo_bloqueo(
        pedido
    )

    detalle.refresh_from_db()

    return detalle


@transaction.atomic
def eliminar_detalle_pedido(*, detalle_id):
    """
    Elimina una línea del carrito y recalcula encabezado.
    """

    detalle = (
        PedidoDetalle.objects
        .select_for_update()
        .select_related("pedido")
        .get(pk=detalle_id)
    )

    pedido = (
        Pedido.objects
        .select_for_update()
        .get(pk=detalle.pedido_id)
    )

    if pedido.estado != "carrito":
        raise ValidationError(
            "Solo se pueden eliminar líneas de un pedido en estado Carrito."
        )

    detalle.delete()

    return _recalcular_pedido_bajo_bloqueo(
        pedido
    )


# ============================================================
# CONFIRMACION DE PEDIDOS E INVENTARIO
# ============================================================

from collections import defaultdict

from django.utils import timezone


@transaction.atomic
def confirmar_pedido(*, pedido_id):
    """
    Confirma un carrito de forma transaccional.

    Garantias:
    - bloquea el pedido;
    - impide doble confirmacion;
    - recalcula totales antes de confirmar;
    - bloquea productos involucrados;
    - agrupa cantidades por producto;
    - valida existencias;
    - descuenta stock una sola vez;
    - registra confirmado_en;
    - ante cualquier error, toda la operacion hace rollback.
    """

    pedido = (
        Pedido.objects
        .select_for_update()
        .select_related("empresa")
        .get(pk=pedido_id)
    )

    # --------------------------------------------------------
    # PROTECCION CONTRA DOBLE CONFIRMACION
    # --------------------------------------------------------

    if pedido.estado != "carrito":
        raise ValidationError(
            "El pedido ya no está en estado Carrito y no puede confirmarse nuevamente."
        )

    # --------------------------------------------------------
    # RECALCULAR IMPORTES ANTES DE CONFIRMAR
    # --------------------------------------------------------

    _recalcular_pedido_bajo_bloqueo(
        pedido
    )

    pedido.refresh_from_db()

    # --------------------------------------------------------
    # BLOQUEAR Y LEER DETALLES
    # --------------------------------------------------------

    detalles = list(
        PedidoDetalle.objects
        .select_for_update()
        .filter(pedido_id=pedido.id)
        .order_by("id")
    )

    if not detalles:
        raise ValidationError(
            "No se puede confirmar un pedido sin productos."
        )

    # --------------------------------------------------------
    # AGRUPAR CANTIDADES POR PRODUCTO
    #
    # Esto es importante si el mismo producto aparece
    # en varias lineas del mismo carrito.
    # --------------------------------------------------------

    cantidades_por_producto = defaultdict(
        lambda: CERO
    )

    for detalle in detalles:

        if detalle.producto_id is None:
            raise ValidationError(
                f"La línea {detalle.id} ya no tiene un producto asociado."
            )

        cantidades_por_producto[
            detalle.producto_id
        ] += decimal_4(
            detalle.cantidad
        )

    producto_ids = sorted(
        cantidades_por_producto.keys()
    )

    # --------------------------------------------------------
    # BLOQUEAR PRODUCTOS
    #
    # El orden por ID ayuda a mantener un orden consistente
    # de locks cuando existan confirmaciones concurrentes.
    # --------------------------------------------------------

    productos = list(
        Producto.objects
        .select_for_update()
        .select_related(
            "catalogo",
            "catalogo__empresa",
        )
        .filter(
            id__in=producto_ids
        )
        .order_by("id")
    )

    productos_por_id = {
        producto.id: producto
        for producto in productos
    }

    if len(productos_por_id) != len(
        producto_ids
    ):
        raise ValidationError(
            "Uno o más productos del pedido ya no existen."
        )

    # --------------------------------------------------------
    # VALIDAR TODO ANTES DE DESCONTAR NADA
    # --------------------------------------------------------

    for producto_id in producto_ids:

        producto = productos_por_id[
            producto_id
        ]

        cantidad_requerida = decimal_4(
            cantidades_por_producto[
                producto_id
            ]
        )

        if not producto.activo:
            raise ValidationError(
                f"El producto {producto.sku} está inactivo."
            )

        if not producto.catalogo.activo:
            raise ValidationError(
                f"El catálogo del producto {producto.sku} está inactivo."
            )

        if (
            producto.catalogo.empresa_id
            != pedido.empresa_id
        ):
            raise ValidationError(
                f"El producto {producto.sku} no pertenece "
                "a la empresa del pedido."
            )

        if (
            producto.catalogo.moneda
            != pedido.moneda
        ):
            raise ValidationError(
                f"La moneda del producto {producto.sku} "
                "no coincide con la moneda del pedido."
            )

        stock_actual = decimal_4(
            producto.stock
        )

        if cantidad_requerida > stock_actual:
            raise ValidationError(
                f"Stock insuficiente para {producto.sku}. "
                f"Disponible: {stock_actual}. "
                f"Requerido: {cantidad_requerida}."
            )

    # --------------------------------------------------------
    # DESCONTAR INVENTARIO
    #
    # Llegamos aqui solamente si TODOS los productos
    # superaron las validaciones.
    # --------------------------------------------------------

    for producto_id in producto_ids:

        producto = productos_por_id[
            producto_id
        ]

        cantidad_requerida = decimal_4(
            cantidades_por_producto[
                producto_id
            ]
        )

        producto.stock = decimal_4(
            producto.stock
            - cantidad_requerida
        )

        producto.save(
            update_fields=[
                "stock",
                "actualizado_en",
            ]
        )

    # --------------------------------------------------------
    # CONFIRMAR PEDIDO
    # --------------------------------------------------------

    pedido.estado = "confirmado"
    pedido.confirmado_en = timezone.now()

    pedido.save(
        update_fields=[
            "estado",
            "confirmado_en",
            "actualizado_en",
        ]
    )

    pedido.refresh_from_db()

    return pedido


from core.models import Canal


# ============================================================
# ACTUALIZACION DE DATOS GENERALES DEL PEDIDO
# ============================================================

@transaction.atomic
def actualizar_datos_pedido(
    *,
    pedido_id,
    canal_id=None,
    cliente_nombre="",
    cliente_telefono="",
    cliente_email="",
    direccion_entrega="",
    notas="",
    identificador_externo="",
):
    """
    Actualiza únicamente información general de un pedido
    mientras permanezca en estado carrito.

    No modifica:
    - empresa
    - moneda
    - subtotal
    - descuento
    - total
    - inventario
    """

    pedido = (
        Pedido.objects
        .select_for_update()
        .select_related("empresa")
        .get(pk=pedido_id)
    )

    if pedido.estado != "carrito":
        raise ValidationError(
            "Solo se puede editar un pedido que esté en estado Carrito."
        )

    canal = None

    if canal_id is not None:

        canal = (
            Canal.objects
            .select_related(
                "bot",
                "bot__empresa",
            )
            .get(pk=canal_id)
        )

        if canal.bot.empresa_id != pedido.empresa_id:
            raise ValidationError(
                "El canal seleccionado no pertenece a la empresa del pedido."
            )

        if not canal.activo:
            raise ValidationError(
                "El canal seleccionado está inactivo."
            )

    pedido.canal = canal
    pedido.cliente_nombre = str(
        cliente_nombre or ""
    ).strip()

    pedido.cliente_telefono = str(
        cliente_telefono or ""
    ).strip()

    pedido.cliente_email = str(
        cliente_email or ""
    ).strip()

    pedido.direccion_entrega = str(
        direccion_entrega or ""
    ).strip()

    pedido.notas = str(
        notas or ""
    ).strip()

    pedido.identificador_externo = str(
        identificador_externo or ""
    ).strip()

    pedido.save(
        update_fields=[
            "canal",
            "cliente_nombre",
            "cliente_telefono",
            "cliente_email",
            "direccion_entrega",
            "notas",
            "identificador_externo",
            "actualizado_en",
        ]
    )

    pedido.refresh_from_db()

    return pedido


# ============================================================
# ACTUALIZACION DE DATOS GENERALES DEL PEDIDO
# ============================================================

@transaction.atomic
def actualizar_datos_pedido(
    *,
    pedido_id,
    canal_id=None,
    cliente_nombre="",
    cliente_telefono="",
    cliente_email="",
    direccion_entrega="",
    notas="",
    identificador_externo="",
):
    """
    Actualiza únicamente información general de un pedido
    mientras permanezca en estado carrito.

    No modifica:
    - empresa
    - moneda
    - subtotal
    - descuento
    - total
    - inventario
    """

    pedido = (
        Pedido.objects
        .select_for_update()
        .select_related("empresa")
        .get(pk=pedido_id)
    )

    if pedido.estado != "carrito":
        raise ValidationError(
            "Solo se puede editar un pedido que esté en estado Carrito."
        )

    canal = None

    if canal_id is not None:

        canal = (
            Canal.objects
            .select_related(
                "bot",
                "bot__empresa",
            )
            .get(pk=canal_id)
        )

        if canal.bot.empresa_id != pedido.empresa_id:
            raise ValidationError(
                "El canal seleccionado no pertenece a la empresa del pedido."
            )

        if not canal.activo:
            raise ValidationError(
                "El canal seleccionado está inactivo."
            )

    pedido.canal = canal
    pedido.cliente_nombre = str(
        cliente_nombre or ""
    ).strip()

    pedido.cliente_telefono = str(
        cliente_telefono or ""
    ).strip()

    pedido.cliente_email = str(
        cliente_email or ""
    ).strip()

    pedido.direccion_entrega = str(
        direccion_entrega or ""
    ).strip()

    pedido.notas = str(
        notas or ""
    ).strip()

    pedido.identificador_externo = str(
        identificador_externo or ""
    ).strip()

    pedido.save(
        update_fields=[
            "canal",
            "cliente_nombre",
            "cliente_telefono",
            "cliente_email",
            "direccion_entrega",
            "notas",
            "identificador_externo",
            "actualizado_en",
        ]
    )

    pedido.refresh_from_db()

    return pedido
