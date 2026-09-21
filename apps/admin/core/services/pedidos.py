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


# ============================================================
# TNL-RESTAURANTE-CENTAVOS-EXACTOS-V1
# La BD conserva 4 decimales.
# Restaurante sólo acepta importes cobrables exactamente
# representables a centavos.
# NUNCA redondea silenciosamente.
# ============================================================


def validar_importe_cobrable_restaurante(
    valor,
    *,
    etiqueta="El importe",
):
    valor_4 = decimal_4(
        valor
    )

    valor_2 = valor_4.quantize(
        Decimal("0.01")
    )

    if valor_4 != valor_2:
        raise ValidationError(
            (
                f"{etiqueta} debe expresarse "
                "exactamente en centavos; "
                "no se permiten fracciones "
                "monetarias menores a $0.01."
            )
        )

    return valor_4


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
    Recalcula el pedido conservando compatibilidad histórica.

    Contrato legacy:
      subtotal = suma cantidad * precio_unitario
      descuento = suma descuentos de línea

    Extensión restaurante:
      subtotal_productos
      subtotal_modificadores
      subtotal_extras
      costo_envio

    Pedido.total continúa siendo la única autoridad cobrable.
    """

    from core.models import (
        ConfiguracionRestaurante,
    )

    detalles = (
        PedidoDetalle.objects
        .select_for_update()
        .filter(
            pedido_id=pedido.id
        )
        .order_by("id")
    )

    subtotal = CERO
    subtotal_productos = CERO
    subtotal_modificadores = CERO
    subtotal_extras = CERO

    descuento_total = CERO
    total_lineas = CERO

    for detalle in detalles:

        cantidad = decimal_4(
            detalle.cantidad
        )

        precio_unitario = decimal_4(
            detalle.precio_unitario
        )

        precio_modificadores = decimal_4(
            detalle.precio_modificadores
        )

        precio_extras = decimal_4(
            detalle.precio_extras
        )

        # Compatibilidad histórica:
        # líneas anteriores a 0025 tienen precio_base=NULL.
        if detalle.precio_base is None:

            precio_base = decimal_4(
                precio_unitario
                -
                precio_modificadores
                -
                precio_extras
            )

        else:

            precio_base = decimal_4(
                detalle.precio_base
            )

            precio_esperado = decimal_4(
                precio_base
                +
                precio_modificadores
                +
                precio_extras
            )

            if (
                precio_esperado
                !=
                precio_unitario
            ):
                raise ValidationError(
                    (
                        f"La línea {detalle.id} tiene "
                        "un desglose de precio inconsistente."
                    )
                )

        if precio_base < CERO:
            raise ValidationError(
                (
                    f"La línea {detalle.id} tiene "
                    "un precio base inválido."
                )
            )

        descuento = decimal_4(
            detalle.descuento
        )

        bruto = decimal_4(
            cantidad
            *
            precio_unitario
        )

        if descuento > bruto:
            raise ValidationError(
                (
                    f"El descuento de la línea {detalle.id} "
                    "no puede ser mayor que su importe bruto."
                )
            )

        importe = decimal_4(
            bruto
            -
            descuento
        )

        if detalle.importe != importe:

            detalle.importe = importe

            detalle.save(
                update_fields=[
                    "importe",
                ]
            )

        subtotal += bruto

        subtotal_productos += decimal_4(
            cantidad
            *
            precio_base
        )

        subtotal_modificadores += decimal_4(
            cantidad
            *
            precio_modificadores
        )

        subtotal_extras += decimal_4(
            cantidad
            *
            precio_extras
        )

        descuento_total += descuento
        total_lineas += importe

    subtotal = decimal_4(
        subtotal
    )

    subtotal_productos = decimal_4(
        subtotal_productos
    )

    subtotal_modificadores = decimal_4(
        subtotal_modificadores
    )

    subtotal_extras = decimal_4(
        subtotal_extras
    )

    desglose_total = decimal_4(
        subtotal_productos
        +
        subtotal_modificadores
        +
        subtotal_extras
    )

    if desglose_total != subtotal:
        raise ValidationError(
            "El desglose económico del pedido no coincide con el subtotal."
        )

    tipo_orden = str(
        pedido.tipo_orden
        or ""
    ).strip()

    costo_envio = CERO

    if tipo_orden == "domicilio":

        configuracion = (
            ConfiguracionRestaurante.objects
            .select_for_update()
            .filter(
                empresa_id=
                    pedido.empresa_id,
                habilitada=True,
            )
            .first()
        )

        if configuracion is None:
            raise ValidationError(
                (
                    "El restaurante no tiene "
                    "configuración de envío activa."
                )
            )

        costo_envio_configurado = (
            validar_importe_cobrable_restaurante(
                configuracion.costo_envio_fijo,
                etiqueta=(
                    "El costo fijo de envío"
                ),
            )
        )

        envio_gratis_desde = (
            configuracion.envio_gratis_desde
        )

        if (
            envio_gratis_desde is not None
            and
            subtotal
            >=
            decimal_4(
                envio_gratis_desde
            )
        ):
            costo_envio = CERO

        else:
            costo_envio = (
                costo_envio_configurado
            )

    elif tipo_orden in {
        "",
        "comedor",
        "para_llevar",
    }:
        costo_envio = CERO

    else:
        raise ValidationError(
            "El tipo de orden del pedido no es válido."
        )

    total_pedido = decimal_4(
        total_lineas
        +
        costo_envio
    )

    if tipo_orden in {
        "comedor",
        "para_llevar",
        "domicilio",
    }:
        subtotal = (
            validar_importe_cobrable_restaurante(
                subtotal,
                etiqueta=(
                    "El subtotal del pedido"
                ),
            )
        )

        descuento_total = (
            validar_importe_cobrable_restaurante(
                descuento_total,
                etiqueta=(
                    "El descuento total del pedido"
                ),
            )
        )

        costo_envio = (
            validar_importe_cobrable_restaurante(
                costo_envio,
                etiqueta=(
                    "El costo de envío del pedido"
                ),
            )
        )

        total_pedido = (
            validar_importe_cobrable_restaurante(
                total_pedido,
                etiqueta=(
                    "El total del pedido"
                ),
            )
        )

    pedido.subtotal = subtotal

    pedido.subtotal_productos = (
        subtotal_productos
    )

    pedido.subtotal_modificadores = (
        subtotal_modificadores
    )

    pedido.subtotal_extras = (
        subtotal_extras
    )

    pedido.costo_envio = decimal_4(
        costo_envio
    )

    pedido.descuento = decimal_4(
        descuento_total
    )

    pedido.total = total_pedido

    pedido.save(
        update_fields=[
            "subtotal",
            "subtotal_productos",
            "subtotal_modificadores",
            "subtotal_extras",
            "costo_envio",
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


# ============================================================
# TNL-PEDIDO-STATUS-RAPIDO-V1
# ============================================================

# =============================================================================
# TNL-RESTAURANTE-ESTADOS-R3-V1
#
# Motor único de avance operativo:
#
# Legacy:
#   confirmado/pagado -> preparando -> enviado -> entregado
#
# Restaurante domicilio:
#   confirmado/pagado -> preparando -> listo -> en_camino -> entregado
#
# Restaurante comedor / para llevar:
#   confirmado/pagado -> preparando -> listo -> entregado
#
# PedidoEstadoEvento se crea dentro de la misma transacción del cambio.
# Esta capa NO envía WhatsApp.
# =============================================================================


ESTADOS_OPERATIVOS_RAPIDOS_PEDIDO = (
    "preparando",
    "listo",
    "en_camino",
    "enviado",
    "entregado",
)


_TRANSICIONES_OPERATIVAS_PEDIDO = {

    "confirmado":
        "preparando",

    "pagado":
        "preparando",

    "preparando":
        "enviado",

    "enviado":
        "entregado",
}


_TRANSICIONES_OPERATIVAS_RESTAURANTE = {

    "confirmado":
        "preparando",

    "pagado":
        "preparando",

    "preparando":
        "listo",
}


def siguiente_estado_operativo_pedido(
    estado_actual,
    *,
    tipo_orden="",
):
    """
    Resuelve exclusivamente el siguiente estado operativo.

    Legacy:
      confirmado/pagado -> preparando -> enviado -> entregado

    Restaurante:
      domicilio:
        confirmado/pagado -> preparando -> listo
        -> en_camino -> entregado

      comedor / para_llevar:
        confirmado/pagado -> preparando -> listo -> entregado
    """

    estado_actual = str(
        estado_actual
        or ""
    ).strip().lower()

    tipo_orden = str(
        tipo_orden
        or ""
    ).strip().lower()

    tipos_restaurante = {
        "comedor",
        "para_llevar",
        "domicilio",
    }

    if (
        tipo_orden
        not in
        tipos_restaurante
    ):

        return (
            _TRANSICIONES_OPERATIVAS_PEDIDO.get(
                estado_actual,
                "",
            )
        )

    siguiente = (
        _TRANSICIONES_OPERATIVAS_RESTAURANTE.get(
            estado_actual
        )
    )

    if siguiente:

        return siguiente

    if estado_actual == "listo":

        if tipo_orden == "domicilio":

            return "en_camino"

        return "entregado"

    if (
        estado_actual == "en_camino"
        and
        tipo_orden == "domicilio"
    ):

        return "entregado"

    return ""



# =============================================================================
# TNL-RESTAURANTE-CANCELACION-PANEL-R6-V1
#
# Cancelación administrativa separada del motor de avance operativo.
#
# Primera fase:
#   Empresa 7 / CHANGO únicamente.
#
# Garantías:
# - transaction.atomic;
# - select_for_update;
# - mismo estado cancelado = idempotente;
# - cada cancelación real crea PedidoEstadoEvento;
# - no modifica inventario;
# - no modifica Pago;
# - no realiza reembolsos;
# - no envía WhatsApp dentro de la transacción.
# =============================================================================

# TNL-RESTAURANTE-CANCELACION-PANEL-REUSABLE-V1
# La cancelación ya no depende de una Empresa concreta.
# cancelar_pedido_administrativo valida tipo_orden Restaurante.


def cancelar_pedido_administrativo(
    *,
    pedido_id,
    usuario_id=None,
) -> dict:
    """
    Cancela administrativamente un pedido Restaurante habilitado.

    La cancelación NO forma parte del avance operativo secuencial.
    """

    from django.contrib.auth import (
        get_user_model,
    )

    from django.core.exceptions import (
        ValidationError,
    )

    from django.db import (
        transaction,
    )

    from core.models import (
        Pedido,
        PedidoEstadoEvento,
    )

    try:
        pedido_id = int(
            pedido_id
        )
    except (
        TypeError,
        ValueError,
    ):
        raise ValidationError(
            "El pedido no es válido."
        )

    if pedido_id <= 0:
        raise ValidationError(
            "El pedido no es válido."
        )

    if usuario_id in (
        "",
        None,
    ):
        usuario_id = None

    else:
        try:
            usuario_id = int(
                usuario_id
            )
        except (
            TypeError,
            ValueError,
        ):
            raise ValidationError(
                "El usuario del cambio no es válido."
            )

        if usuario_id <= 0:
            raise ValidationError(
                "El usuario del cambio no es válido."
            )

        User = get_user_model()

        if not User.objects.filter(
            pk=usuario_id
        ).exists():
            raise ValidationError(
                "El usuario del cambio no existe."
            )

    estados_cancelables = {
        "pendiente",
        "confirmado",
        "pagado",
        "preparando",
        "listo",
        "en_camino",
        "enviado",
    }

    tipos_restaurante = {
        "comedor",
        "para_llevar",
        "domicilio",
    }

    with transaction.atomic():

        pedido = (
            Pedido.objects
            .select_for_update(
                of=("self",)
            )
            .select_related(
                "empresa",
                "canal",
                "canal__bot",
            )
            .get(
                pk=pedido_id
            )
        )

        tipo_orden = str(
            pedido.tipo_orden
            or ""
        ).strip().lower()

        if tipo_orden not in tipos_restaurante:
            raise ValidationError(
                "La cancelación administrativa sólo está habilitada para pedidos Restaurante."
            )

        estado_anterior = str(
            pedido.estado
            or ""
        ).strip().lower()

        # Retry / doble clic.
        if estado_anterior == "cancelado":
            return {
                "pedido":
                    pedido,

                "cambio_real":
                    False,

                "estado_anterior":
                    estado_anterior,

                "estado_nuevo":
                    "cancelado",

                "evento":
                    None,
            }

        if estado_anterior not in estados_cancelables:
            raise ValidationError(
                (
                    "El pedido en estado "
                    f"{pedido.get_estado_display()} "
                    "no se puede cancelar desde el panel."
                )
            )

        pedido.estado = "cancelado"

        pedido.save(
            update_fields=[
                "estado",
                "actualizado_en",
            ]
        )

        evento = (
            PedidoEstadoEvento.objects.create(
                pedido=pedido,

                estado_anterior=
                    estado_anterior,

                estado_nuevo=
                    "cancelado",

                usuario_id=
                    usuario_id,
            )
        )

        pedido.refresh_from_db()

        return {
            "pedido":
                pedido,

            "cambio_real":
                True,

            "estado_anterior":
                estado_anterior,

            "estado_nuevo":
                "cancelado",

            "evento":
                evento,
        }


# =============================================================================
# TNL-CANCELACION-CLIENTE-V1
#
# Cancelación solicitada por el CLIENTE desde WhatsApp
# (botón de Typebot o texto explícito atendido por la IA).
#
# Es la única regla autorizada para ambos caminos:
# - carrito / confirmado  -> cancelado + PedidoEstadoEvento;
# - cancelado             -> idempotente, sin evento nuevo;
# - cualquier otro estado -> ValidationError, sin modificar el pedido.
#
# Garantías:
# - transaction.atomic + select_for_update;
# - el estado se vuelve a leer después del bloqueo;
# - no modifica inventario, Pago ni reembolsos.
# =============================================================================


def cancelar_pedido_cliente(
    *,
    pedido_id,
) -> dict:
    """
    Cancela un pedido a petición del cliente.

    Lanza ValidationError si el estado actual del
    pedido ya no permite la cancelación.
    """

    from django.core.exceptions import (
        ValidationError,
    )

    from django.db import (
        transaction,
    )

    from core.models import (
        Pedido,
        PedidoEstadoEvento,
    )

    try:
        pedido_id = int(
            pedido_id
        )
    except (
        TypeError,
        ValueError,
    ):
        raise ValidationError(
            "El pedido no es válido."
        )

    if pedido_id <= 0:
        raise ValidationError(
            "El pedido no es válido."
        )

    estados_cancelables = {
        "carrito",
        "confirmado",
    }

    with transaction.atomic():

        pedido = (
            Pedido.objects
            .select_for_update(
                of=("self",)
            )
            .get(
                pk=pedido_id
            )
        )

        estado_anterior = str(
            pedido.estado
            or ""
        ).strip().lower()

        # Reintento / webhook duplicado.
        if estado_anterior == "cancelado":
            return {
                "pedido":
                    pedido,

                "cambio_real":
                    False,

                "estado_anterior":
                    estado_anterior,

                "estado_nuevo":
                    "cancelado",

                "evento":
                    None,
            }

        if estado_anterior not in estados_cancelables:
            raise ValidationError(
                (
                    f"El pedido {pedido.numero} está en estado "
                    f"{pedido.get_estado_display()} y ya no se puede "
                    "cancelar desde WhatsApp. Si necesitas ayuda, "
                    "comunícate con el restaurante."
                )
            )

        pedido.estado = "cancelado"

        pedido.save(
            update_fields=[
                "estado",
                "actualizado_en",
            ]
        )

        evento = (
            PedidoEstadoEvento.objects.create(
                pedido=pedido,

                estado_anterior=
                    estado_anterior,

                estado_nuevo=
                    "cancelado",

                usuario_id=
                    None,
            )
        )

        pedido.refresh_from_db()

        return {
            "pedido":
                pedido,

            "cambio_real":
                True,

            "estado_anterior":
                estado_anterior,

            "estado_nuevo":
                "cancelado",

            "evento":
                evento,
        }




# =============================================================================
# TNL-COCINA-PAGO-P5-V1
#
# Gate financiero exclusivamente para el primer salto operativo
# Restaurante:
#
#     confirmado -> preparando
#
# Scope inicial:
#     Empresa 7 / CHANGO.
#
# No modifica Pago.
# No bloquea Pago con select_for_update.
# No altera estados operativos ya iniciados.
# No modifica la semántica pura de siguiente_estado_operativo_pedido().
# =============================================================================

def evaluar_inicio_preparacion_pedido(
    pedido,
) -> dict:

    from core.models import (
        Pago,
    )


    tipos_restaurante = {
        "comedor",
        "para_llevar",
        "domicilio",
    }


    empresa_id = getattr(
        pedido,
        "empresa_id",
        None,
    )

    tipo_orden = str(
        getattr(
            pedido,
            "tipo_orden",
            "",
        )
        or
        ""
    ).strip().lower()

    estado_pedido = str(
        getattr(
            pedido,
            "estado",
            "",
        )
        or
        ""
    ).strip().lower()


    # -------------------------------------------------------------
    # El gate no cambia legacy, otras empresas ni estados posteriores.
    # -------------------------------------------------------------

    if (
        empresa_id != 7
        or
        tipo_orden
        not in
        tipos_restaurante
        or
        estado_pedido
        !=
        "confirmado"
    ):

        return {
            "aplica":
                False,

            "permitido":
                True,

            "motivo":
                "fuera_scope",

            "mensaje":
                "",
        }


    # Lectura deliberadamente SIN select_for_update.
    #
    # El Pedido ya está bloqueado en cambiar_estado_pedido().
    # P2 también serializa sobre Pedido.
    #
    # P4, en cambio, bloquea Pago -> Pedido. Evitamos adquirir aquí
    # el lock inverso Pedido -> Pago para no introducir un deadlock.
    pagos = list(
        pedido.pagos.all()
    )


    if not pagos:

        return {
            "aplica":
                True,

            "permitido":
                False,

            "motivo":
                "sin_pago",

            "mensaje":
                (
                    "Antes de comenzar la preparación "
                    "debes registrar el método de pago "
                    "del pedido."
                ),
        }


    # -------------------------------------------------------------
    # FAIL-CLOSED:
    #
    # cualquier Checkout Mercado Pago todavía activo impide cocina,
    # incluso si hubiera registros financieros inconsistentes.
    # -------------------------------------------------------------

    mp_activo = any(
        pago.proveedor
        ==
        Pago.Proveedor.MERCADOPAGO
        and
        pago.estado
        in {
            Pago.Estado.CREADO,
            Pago.Estado.PENDIENTE,
        }
        for pago in pagos
    )


    if mp_activo:

        return {
            "aplica":
                True,

            "permitido":
                False,

            "motivo":
                "mercadopago_pendiente",

            "mensaje":
                (
                    "El pago con Mercado Pago todavía "
                    "no está aprobado. Espera la "
                    "confirmación automática antes "
                    "de comenzar la preparación."
                ),
        }


    mp_aprobado = any(
        pago.proveedor
        ==
        Pago.Proveedor.MERCADOPAGO
        and
        pago.estado
        ==
        Pago.Estado.APROBADO
        for pago in pagos
    )


    if mp_aprobado:

        return {
            "aplica":
                True,

            "permitido":
                True,

            "motivo":
                "mercadopago_aprobado",

            "mensaje":
                "",
        }


    pago_negocio = any(
        pago.proveedor
        ==
        Pago.Proveedor.NEGOCIO
        and
        pago.estado
        in {
            Pago.Estado.PENDIENTE,
            Pago.Estado.APROBADO,
        }
        for pago in pagos
    )


    if pago_negocio:

        return {
            "aplica":
                True,

            "permitido":
                True,

            "motivo":
                "pago_negocio",

            "mensaje":
                "",
        }


    return {
        "aplica":
            True,

        "permitido":
            False,

        "motivo":
            "sin_pago_habilitante",

        "mensaje":
            (
                "El pedido no tiene un estado de pago "
                "que permita comenzar la preparación."
            ),
    }


def cambiar_estado_pedido(
    *,
    pedido_id,
    nuevo_estado,
    usuario_id=None,
) -> dict:
    """
    Avanza secuencialmente el estado operativo del pedido.

    Garantías:
    - transaction.atomic;
    - select_for_update;
    - no saltos;
    - no retrocesos;
    - mismo estado = operación idempotente;
    - cada cambio real crea un único PedidoEstadoEvento;
    - el evento comparte la misma transacción del pedido;
    - no modifica inventario;
    - no envía WhatsApp.
    """

    from django.contrib.auth import (
        get_user_model,
    )

    from django.core.exceptions import (
        ValidationError,
    )

    from django.db import (
        transaction,
    )

    from core.models import (
        Pedido,
        PedidoEstadoEvento,
    )


    try:

        pedido_id = int(
            pedido_id
        )

    except (
        TypeError,
        ValueError,
    ):

        raise ValidationError(
            "El pedido no es válido."
        )


    if pedido_id <= 0:

        raise ValidationError(
            "El pedido no es válido."
        )


    nuevo_estado = str(
        nuevo_estado
        or ""
    ).strip().lower()


    if (
        nuevo_estado
        not in
        ESTADOS_OPERATIVOS_RAPIDOS_PEDIDO
    ):

        raise ValidationError(
            "El estado solicitado no está permitido."
        )


    if usuario_id in (
        "",
        None,
    ):

        usuario_id = None

    else:

        try:

            usuario_id = int(
                usuario_id
            )

        except (
            TypeError,
            ValueError,
        ):

            raise ValidationError(
                "El usuario del cambio no es válido."
            )

        if usuario_id <= 0:

            raise ValidationError(
                "El usuario del cambio no es válido."
            )

        User = get_user_model()

        if not User.objects.filter(
            pk=usuario_id
        ).exists():

            raise ValidationError(
                "El usuario del cambio no existe."
            )


    with transaction.atomic():

        pedido = (
            Pedido.objects
            .select_for_update(
                of=("self",)
            )
            .select_related(
                "empresa",
                "canal",
                "canal__bot",
            )
            .get(
                pk=pedido_id
            )
        )


        estado_anterior = str(
            pedido.estado
            or ""
        ).strip().lower()


        # Retry / doble clic:
        # no produce transición ni evento duplicado.
        if (
            estado_anterior
            ==
            nuevo_estado
        ):

            return {
                "pedido":
                    pedido,

                "cambio_real":
                    False,

                "estado_anterior":
                    estado_anterior,

                "estado_nuevo":
                    nuevo_estado,

                "evento":
                    None,
            }


        estado_esperado = (
            siguiente_estado_operativo_pedido(
                estado_anterior,
                tipo_orden=
                    pedido.tipo_orden,
            )
        )


        if not estado_esperado:

            raise ValidationError(
                (
                    "El pedido en estado "
                    f"{pedido.get_estado_display()} "
                    "no admite un avance rápido."
                )
            )


        if (
            nuevo_estado
            !=
            estado_esperado
        ):

            label_siguiente = (
                dict(
                    Pedido.ESTADOS
                ).get(
                    estado_esperado,
                    estado_esperado,
                )
            )

            raise ValidationError(
                (
                    "Cambio de estado no permitido. "
                    f"Desde {pedido.get_estado_display()} "
                    f"el siguiente estado válido es "
                    f"{label_siguiente}."
                )
            )



        # =============================================================
        # TNL-COCINA-PAGO-P5-V1
        #
        # Sólo el primer salto Restaurante confirmado -> preparando
        # requiere autorización financiera en CHANGO.
        # =============================================================

        if (
            estado_anterior
            ==
            "confirmado"
            and
            nuevo_estado
            ==
            "preparando"
        ):

            gate_preparacion = (
                evaluar_inicio_preparacion_pedido(
                    pedido
                )
            )

            if (
                gate_preparacion[
                    "aplica"
                ]
                and
                not gate_preparacion[
                    "permitido"
                ]
            ):

                raise ValidationError(
                    gate_preparacion[
                        "mensaje"
                    ]
                )


        pedido.estado = (
            nuevo_estado
        )

        pedido.save(
            update_fields=[
                "estado",
                "actualizado_en",
            ]
        )


        evento = (
            PedidoEstadoEvento.objects.create(
                pedido=pedido,

                estado_anterior=
                    estado_anterior,

                estado_nuevo=
                    nuevo_estado,

                usuario_id=
                    usuario_id,
            )
        )


        pedido.refresh_from_db()


        return {
            "pedido":
                pedido,

            "cambio_real":
                True,

            "estado_anterior":
                estado_anterior,

            "estado_nuevo":
                nuevo_estado,

            "evento":
                evento,
        }




# =============================================================================
# TNL-PAGO-DIRECTO-P3-V1
#
# Confirmación financiera manual de Efectivo / contra entrega.
#
# NO forma parte del motor de avance operativo.
# NO genera PedidoEstadoEvento.
# NO envía WhatsApp.
# NO modifica pagos Mercado Pago.
# =============================================================================

def marcar_pago_directo_pagado(
    *,
    pedido_id,
) -> dict:

    from django.core.exceptions import (
        ValidationError,
    )

    from django.db import (
        transaction,
    )

    from django.utils import (
        timezone,
    )

    from core.models import (
        Pago,
        Pedido,
    )


    try:

        pedido_id = int(
            pedido_id
        )

    except (
        TypeError,
        ValueError,
    ):

        raise ValidationError(
            "El pedido no es válido."
        )


    if pedido_id <= 0:

        raise ValidationError(
            "El pedido no es válido."
        )


    tipos_restaurante = {
        "comedor",
        "para_llevar",
        "domicilio",
    }


    estados_pago_manual_permitidos = {
        "pendiente",
        "confirmado",
        "pagado",
        "preparando",
        "listo",
        "en_camino",
        "enviado",
        "entregado",
    }


    with transaction.atomic():

        pedido = (
            Pedido.objects
            .select_for_update(
                of=("self",)
            )
            .select_related(
                "empresa",
                "canal",
                "canal__bot",
            )
            .get(
                pk=pedido_id
            )
        )


        if pedido.empresa_id != 7:

            raise ValidationError(
                (
                    "El pago manual todavía "
                    "no está habilitado "
                    "para esta empresa."
                )
            )


        tipo_orden = str(
            pedido.tipo_orden
            or ""
        ).strip().lower()


        if (
            tipo_orden
            not in
            tipos_restaurante
        ):

            raise ValidationError(
                (
                    "El pago manual sólo está "
                    "habilitado para pedidos "
                    "Restaurante."
                )
            )


        estado_pedido_anterior = str(
            pedido.estado
            or ""
        ).strip().lower()


        if (
            estado_pedido_anterior
            not in
            estados_pago_manual_permitidos
        ):

            raise ValidationError(
                (
                    "El pedido en estado "
                    f"{pedido.get_estado_display()} "
                    "no permite registrar "
                    "el pago manual."
                )
            )


        # -------------------------------------------------------------
        # Exclusión financiera:
        # si existe un MP activo/aprobado no se permite confirmar
        # manualmente un pago con el negocio.
        # -------------------------------------------------------------

        pago_mp_conflictivo = (
            Pago.objects
            .filter(
                pedido=
                    pedido,

                proveedor=
                    Pago.Proveedor
                    .MERCADOPAGO,

                estado__in=[
                    Pago.Estado.CREADO,
                    Pago.Estado.PENDIENTE,
                    Pago.Estado.APROBADO,
                ],
            )
            .exists()
        )


        if pago_mp_conflictivo:

            raise ValidationError(
                (
                    "Este pedido tiene un proceso "
                    "de Mercado Pago activo "
                    "o aprobado."
                )
            )


        # -------------------------------------------------------------
        # Mismo criterio que Punto 2:
        # el registro financiero vigente es el último Pago negocio.
        # -------------------------------------------------------------

        pago = (
            Pago.objects
            .select_for_update()
            .filter(
                pedido=
                    pedido,

                proveedor=
                    Pago.Proveedor
                    .NEGOCIO,
            )
            .order_by(
                "-id"
            )
            .first()
        )


        if pago is None:

            raise ValidationError(
                (
                    "Este pedido no tiene "
                    "un pago en efectivo "
                    "o contra entrega registrado."
                )
            )


        # Retry / doble clic:
        # ya está financieramente aprobado.
        if (
            pago.estado
            ==
            Pago.Estado.APROBADO
        ):

            return {
                "pedido":
                    pedido,

                "pago":
                    pago,

                "cambio_real":
                    False,

                "pedido_cambio_real":
                    False,

                "pedido_estado_anterior":
                    estado_pedido_anterior,

                "pedido_estado_nuevo":
                    estado_pedido_anterior,
            }


        if (
            pago.estado
            !=
            Pago.Estado.PENDIENTE
        ):

            raise ValidationError(
                (
                    "El pago directo se encuentra "
                    f"en estado {pago.get_estado_display()} "
                    "y no puede marcarse como pagado."
                )
            )


        pago.estado = (
            Pago.Estado.APROBADO
        )


        if pago.aprobado_en is None:

            pago.aprobado_en = (
                timezone.now()
            )


        pago.save(
            update_fields=[
                "estado",
                "aprobado_en",
                "actualizado_en",
            ]
        )


        pedido_cambio_real = False
        pedido_estado_nuevo = (
            estado_pedido_anterior
        )


        # Igual que Mercado Pago:
        # sólo pendiente/confirmado pasan a pagado.
        if (
            estado_pedido_anterior
            in {
                "pendiente",
                "confirmado",
            }
        ):

            pedido.estado = (
                "pagado"
            )

            pedido.save(
                update_fields=[
                    "estado",
                    "actualizado_en",
                ]
            )

            pedido_cambio_real = True
            pedido_estado_nuevo = (
                "pagado"
            )


        # Estados operativos posteriores no se degradan.
        # Tampoco se genera PedidoEstadoEvento porque
        # la transición es financiera, igual que MP.


        pago.refresh_from_db()
        pedido.refresh_from_db()


        return {
            "pedido":
                pedido,

            "pago":
                pago,

            "cambio_real":
                True,

            "pedido_cambio_real":
                pedido_cambio_real,

            "pedido_estado_anterior":
                estado_pedido_anterior,

            "pedido_estado_nuevo":
                pedido_estado_nuevo,
        }




# ============================================================
# TNL-RESTAURANTE-MOTOR-PEDIDOS-V1
# Configuración de productos + logística.
#
# No reemplaza el endpoint Typebot legacy.
# ============================================================


def _normalizar_ids_opciones_restaurante(
    valores,
):
    """
    Convierte la selección de opciones en IDs enteros únicos.
    """

    if valores is None:
        return []

    if not isinstance(
        valores,
        (
            list,
            tuple,
            set,
        ),
    ):
        raise ValidationError(
            (
                "Las opciones seleccionadas "
                "deben enviarse como una lista."
            )
        )

    resultado = []
    vistos = set()

    for valor in valores:

        try:
            opcion_id = int(
                valor
            )

        except (
            TypeError,
            ValueError,
        ):
            raise ValidationError(
                "Existe una opción seleccionada inválida."
            )

        if opcion_id <= 0:
            raise ValidationError(
                "Existe una opción seleccionada inválida."
            )

        if opcion_id in vistos:
            raise ValidationError(
                "No se puede seleccionar dos veces la misma opción."
            )

        vistos.add(
            opcion_id
        )

        resultado.append(
            opcion_id
        )

    return resultado


def _resolver_configuracion_producto_restaurante(
    *,
    producto,
    seleccion_opciones,
):
    """
    Valida grupos/opciones y construye snapshots económicos.

    Retorna:
      precio_modificadores
      precio_extras
      modificadores_snapshot
      extras_snapshot
    """

    from core.models import (
        GrupoModificadorProducto,
        OpcionModificadorProducto,
    )

    opcion_ids = (
        _normalizar_ids_opciones_restaurante(
            seleccion_opciones
        )
    )

    grupos = list(
        GrupoModificadorProducto.objects
        .select_for_update()
        .filter(
            producto_id=producto.id,
            activo=True,
        )
        .order_by(
            "orden",
            "id",
        )
    )

    grupos_por_id = {
        grupo.id:
            grupo
        for grupo in grupos
    }

    opciones = []

    if opcion_ids:

        opciones = list(
            OpcionModificadorProducto.objects
            .select_for_update()
            .select_related(
                "grupo",
            )
            .filter(
                id__in=opcion_ids,
                activa=True,
                grupo__activo=True,
            )
            .order_by(
                "grupo__orden",
                "grupo_id",
                "orden",
                "id",
            )
        )

        encontrados = {
            opcion.id
            for opcion in opciones
        }

        if encontrados != set(
            opcion_ids
        ):
            raise ValidationError(
                (
                    "Una o más opciones seleccionadas "
                    "no existen o están inactivas."
                )
            )

    seleccion_por_grupo = {}

    for opcion in opciones:

        grupo = opcion.grupo

        if grupo.producto_id != producto.id:
            raise ValidationError(
                (
                    "Una opción seleccionada "
                    "no pertenece al producto."
                )
            )

        if grupo.id not in grupos_por_id:
            raise ValidationError(
                (
                    "Una opción seleccionada "
                    "pertenece a un grupo inactivo."
                )
            )

        seleccion_por_grupo.setdefault(
            grupo.id,
            [],
        ).append(
            opcion
        )

    precio_modificadores = CERO
    precio_extras = CERO

    modificadores_snapshot = []
    extras_snapshot = []

    for grupo in grupos:

        seleccionadas = (
            seleccion_por_grupo.get(
                grupo.id,
                [],
            )
        )

        cantidad = len(
            seleccionadas
        )

        minimo = int(
            grupo.minimo
        )

        maximo = int(
            grupo.maximo
        )

        if grupo.obligatorio:

            if cantidad < minimo:
                raise ValidationError(
                    (
                        f"El grupo '{grupo.nombre}' "
                        f"requiere al menos {minimo} "
                        "opción(es)."
                    )
                )

        elif cantidad > 0 and cantidad < minimo:

            raise ValidationError(
                (
                    f"El grupo '{grupo.nombre}' "
                    f"requiere al menos {minimo} "
                    "opción(es) cuando se selecciona."
                )
            )

        if cantidad > maximo:
            raise ValidationError(
                (
                    f"El grupo '{grupo.nombre}' "
                    f"permite máximo {maximo} "
                    "opción(es)."
                )
            )

        if not seleccionadas:
            continue

        opciones_snapshot = []

        total_grupo = CERO

        for opcion in seleccionadas:

            precio_adicional = (
                validar_importe_cobrable_restaurante(
                    opcion.precio_adicional,
                    etiqueta=(
                        "El precio adicional "
                        f"de '{opcion.nombre}'"
                    ),
                )
            )

            total_grupo += (
                precio_adicional
            )

            opciones_snapshot.append(
                {
                    "opcion_id":
                        opcion.id,

                    "nombre":
                        opcion.nombre,

                    "precio_adicional":
                        str(
                            precio_adicional
                        ),
                }
            )

        snapshot = {
            "grupo_id":
                grupo.id,

            "grupo_nombre":
                grupo.nombre,

            "tipo":
                grupo.tipo,

            "opciones":
                opciones_snapshot,
        }

        if (
            grupo.tipo
            ==
            GrupoModificadorProducto
            .Tipo
            .EXTRA
        ):

            precio_extras += (
                total_grupo
            )

            extras_snapshot.append(
                snapshot
            )

        else:

            precio_modificadores += (
                total_grupo
            )

            modificadores_snapshot.append(
                snapshot
            )

    return {
        "precio_modificadores":
            decimal_4(
                precio_modificadores
            ),

        "precio_extras":
            decimal_4(
                precio_extras
            ),

        "modificadores_snapshot":
            modificadores_snapshot,

        "extras_snapshot":
            extras_snapshot,
    }


@transaction.atomic
def agregar_producto_configurado_a_pedido(
    *,
    pedido_id,
    producto_id,
    cantidad,
    seleccion_opciones=None,
    descuento=CERO,
):
    """
    Agrega una línea restaurante usando el motor histórico.

    Cada configuración genera una línea independiente.
    """

    # Reutilizamos todas las validaciones históricas:
    # tenant, moneda, producto, catálogo y cantidad.
    detalle = agregar_producto_a_pedido(
        pedido_id=pedido_id,
        producto_id=producto_id,
        cantidad=cantidad,
        descuento=CERO,
    )

    producto = (
        Producto.objects
        .select_for_update()
        .get(
            pk=producto_id
        )
    )

    configuracion = (
        _resolver_configuracion_producto_restaurante(
            producto=producto,
            seleccion_opciones=
                seleccion_opciones,
        )
    )

    precio_base = (
        validar_importe_cobrable_restaurante(
            producto.precio,
            etiqueta=(
                "El precio base del producto"
            ),
        )
    )

    precio_modificadores = (
        configuracion[
            "precio_modificadores"
        ]
    )

    precio_extras = (
        configuracion[
            "precio_extras"
        ]
    )

    precio_unitario = (
        validar_importe_cobrable_restaurante(
            decimal_4(
                precio_base
                +
                precio_modificadores
                +
                precio_extras
            ),
            etiqueta=(
                "El precio unitario configurado"
            ),
        )
    )

    cantidad_decimal = decimal_4(
        detalle.cantidad
    )

    descuento = (
        validar_importe_cobrable_restaurante(
            descuento,
            etiqueta=(
                "El descuento de la línea"
            ),
        )
    )

    if descuento < CERO:
        raise ValidationError(
            "El descuento no puede ser negativo."
        )

    bruto = (
        validar_importe_cobrable_restaurante(
            decimal_4(
                cantidad_decimal
                *
                precio_unitario
            ),
            etiqueta=(
                "El importe bruto de la línea"
            ),
        )
    )

    if descuento > bruto:
        raise ValidationError(
            (
                "El descuento no puede ser mayor "
                "que el importe bruto de la línea."
            )
        )

    detalle.precio_base = (
        precio_base
    )

    detalle.precio_modificadores = (
        precio_modificadores
    )

    detalle.precio_extras = (
        precio_extras
    )

    detalle.modificadores_snapshot = (
        configuracion[
            "modificadores_snapshot"
        ]
    )

    detalle.extras_snapshot = (
        configuracion[
            "extras_snapshot"
        ]
    )

    detalle.precio_unitario = (
        precio_unitario
    )

    detalle.descuento = descuento

    detalle.importe = (
        validar_importe_cobrable_restaurante(
            decimal_4(
                bruto
                -
                descuento
            ),
            etiqueta=(
                "El importe final de la línea"
            ),
        )
    )

    detalle.save(
        update_fields=[
            "precio_base",
            "precio_modificadores",
            "precio_extras",
            "modificadores_snapshot",
            "extras_snapshot",
            "precio_unitario",
            "descuento",
            "importe",
        ]
    )

    pedido = (
        Pedido.objects
        .select_for_update()
        .get(
            pk=pedido_id
        )
    )

    _recalcular_pedido_bajo_bloqueo(
        pedido
    )

    detalle.refresh_from_db()

    return detalle


@transaction.atomic
def configurar_logistica_pedido(
    *,
    pedido_id,
    tipo_orden,
    direccion_entrega="",
):
    """
    Configura comedor / para llevar / domicilio.

    El costo de envío nunca llega desde Typebot.
    Se calcula desde ConfiguracionRestaurante.
    """

    from core.models import (
        ConfiguracionRestaurante,
    )

    pedido = (
        Pedido.objects
        .select_for_update()
        .get(
            pk=pedido_id
        )
    )

    if pedido.estado != "carrito":
        raise ValidationError(
            (
                "Solo se puede configurar "
                "la logística de un pedido "
                "en estado Carrito."
            )
        )

    tipo_orden = str(
        tipo_orden
        or ""
    ).strip()

    tipos_validos = {
        "comedor",
        "para_llevar",
        "domicilio",
    }

    if tipo_orden not in tipos_validos:
        raise ValidationError(
            "El tipo de orden no es válido."
        )

    configuracion = (
        ConfiguracionRestaurante.objects
        .select_for_update()
        .filter(
            empresa_id=
                pedido.empresa_id,
            habilitada=True,
        )
        .first()
    )

    if configuracion is None:
        raise ValidationError(
            (
                "El restaurante no tiene "
                "configuración activa."
            )
        )

    direccion = str(
        direccion_entrega
        or ""
    ).strip()

    if tipo_orden == "domicilio":

        if not direccion:
            direccion = str(
                pedido.direccion_entrega
                or ""
            ).strip()

        if not direccion:
            raise ValidationError(
                (
                    "La dirección de entrega "
                    "es obligatoria para pedidos "
                    "a domicilio."
                )
            )

    else:
        # Comedor y para llevar no requieren dirección.
        direccion = ""

    pedido.tipo_orden = (
        tipo_orden
    )

    pedido.direccion_entrega = (
        direccion
    )

    pedido.tiempo_estimado_minutos = (
        configuracion
        .tiempo_estimado_minutos
    )

    pedido.save(
        update_fields=[
            "tipo_orden",
            "direccion_entrega",
            "tiempo_estimado_minutos",
            "actualizado_en",
        ]
    )

    return _recalcular_pedido_bajo_bloqueo(
        pedido
    )

