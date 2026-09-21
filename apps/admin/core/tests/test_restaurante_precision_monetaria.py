from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import (
    Empresa,
    Catalogo,
    Producto,
    PedidoDetalle,
    ConfiguracionRestaurante,
    GrupoModificadorProducto,
    OpcionModificadorProducto,
)

from core.services.pedidos import (
    crear_pedido,
    agregar_producto_a_pedido,
    agregar_producto_configurado_a_pedido,
    configurar_logistica_pedido,
    confirmar_pedido,
)


class RestaurantePrecisionMonetariaTests(TestCase):

    def setUp(self):

        self.empresa = Empresa.objects.create(
            nombre="Restaurante Precision TEST",
            rfc="RPM010101AA1",
        )

        self.catalogo = Catalogo.objects.create(
            empresa=self.empresa,
            nombre="Menu Precision TEST",
            moneda="MXN",
            activo=True,
        )

        self.config = (
            ConfiguracionRestaurante.objects.create(
                empresa=self.empresa,
                costo_envio_fijo=Decimal("35.0000"),
                envio_gratis_desde=Decimal("300.0000"),
                tiempo_estimado_minutos=30,
                habilitada=True,
            )
        )

    def crear_producto(
        self,
        *,
        precio,
        nombre="Producto Precision",
    ):
        return Producto.objects.create(
            catalogo=self.catalogo,
            nombre=nombre,
            precio=Decimal(precio),
            stock=Decimal("100.0000"),
            activo=True,
        )

    def crear_pedido(self):
        return crear_pedido(
            empresa_id=self.empresa.id,
            moneda="MXN",
            cliente_nombre="Cliente Precision",
            cliente_telefono="3312345678",
        )

    def test_01_precio_base_mas_de_dos_decimales_rechazado(self):

        producto = self.crear_producto(
            precio="100.1234",
        )

        pedido = self.crear_pedido()

        with self.assertRaisesMessage(
            ValidationError,
            "precio base",
        ):
            agregar_producto_configurado_a_pedido(
                pedido_id=pedido.id,
                producto_id=producto.id,
                cantidad="1.0000",
                seleccion_opciones=[],
            )

        self.assertEqual(
            PedidoDetalle.objects.count(),
            0,
        )

    def test_02_modificador_mas_de_dos_decimales_rechazado(self):

        producto = self.crear_producto(
            precio="100.0000",
        )

        grupo = (
            GrupoModificadorProducto.objects.create(
                producto=producto,
                nombre="Tamaño",
                tipo=(
                    GrupoModificadorProducto
                    .Tipo
                    .MODIFICADOR
                ),
                obligatorio=True,
                minimo=1,
                maximo=1,
                activo=True,
            )
        )

        opcion = (
            OpcionModificadorProducto.objects.create(
                grupo=grupo,
                nombre="Grande",
                precio_adicional=Decimal("20.1250"),
                activa=True,
            )
        )

        pedido = self.crear_pedido()

        with self.assertRaisesMessage(
            ValidationError,
            "precio adicional",
        ):
            agregar_producto_configurado_a_pedido(
                pedido_id=pedido.id,
                producto_id=producto.id,
                cantidad="1.0000",
                seleccion_opciones=[
                    opcion.id,
                ],
            )

    def test_03_extra_mas_de_dos_decimales_rechazado(self):

        producto = self.crear_producto(
            precio="100.0000",
        )

        grupo = (
            GrupoModificadorProducto.objects.create(
                producto=producto,
                nombre="Extras",
                tipo=(
                    GrupoModificadorProducto
                    .Tipo
                    .EXTRA
                ),
                obligatorio=False,
                minimo=0,
                maximo=1,
                activo=True,
            )
        )

        opcion = (
            OpcionModificadorProducto.objects.create(
                grupo=grupo,
                nombre="Queso especial",
                precio_adicional=Decimal("10.5678"),
                activa=True,
            )
        )

        pedido = self.crear_pedido()

        with self.assertRaisesMessage(
            ValidationError,
            "precio adicional",
        ):
            agregar_producto_configurado_a_pedido(
                pedido_id=pedido.id,
                producto_id=producto.id,
                cantidad="1.0000",
                seleccion_opciones=[
                    opcion.id,
                ],
            )

    def test_04_descuento_mas_de_dos_decimales_rechazado(self):

        producto = self.crear_producto(
            precio="100.0000",
        )

        pedido = self.crear_pedido()

        with self.assertRaisesMessage(
            ValidationError,
            "descuento de la línea",
        ):
            agregar_producto_configurado_a_pedido(
                pedido_id=pedido.id,
                producto_id=producto.id,
                cantidad="1.0000",
                seleccion_opciones=[],
                descuento="5.0050",
            )

    def test_05_cantidad_fraccionaria_importe_no_cobrable_rechazado(self):

        producto = self.crear_producto(
            precio="10.0000",
        )

        pedido = self.crear_pedido()

        with self.assertRaisesMessage(
            ValidationError,
            "importe bruto",
        ):
            agregar_producto_configurado_a_pedido(
                pedido_id=pedido.id,
                producto_id=producto.id,
                cantidad="1.2345",
                seleccion_opciones=[],
            )

    def test_06_cantidad_fraccionaria_importe_exactamente_cobrable(self):

        producto = self.crear_producto(
            precio="10.0000",
        )

        pedido = self.crear_pedido()

        detalle = (
            agregar_producto_configurado_a_pedido(
                pedido_id=pedido.id,
                producto_id=producto.id,
                cantidad="1.5000",
                seleccion_opciones=[],
            )
        )

        pedido.refresh_from_db()

        self.assertEqual(
            detalle.importe,
            Decimal("15.0000"),
        )

        self.assertEqual(
            pedido.total,
            Decimal("15.0000"),
        )

    def test_07_costo_envio_no_cobrable_rechazado(self):

        self.config.costo_envio_fijo = (
            Decimal("35.0050")
        )

        self.config.save(
            update_fields=[
                "costo_envio_fijo",
            ]
        )

        producto = self.crear_producto(
            precio="100.0000",
        )

        pedido = self.crear_pedido()

        agregar_producto_configurado_a_pedido(
            pedido_id=pedido.id,
            producto_id=producto.id,
            cantidad="1.0000",
            seleccion_opciones=[],
        )

        with self.assertRaisesMessage(
            ValidationError,
            "costo fijo de envío",
        ):
            configurar_logistica_pedido(
                pedido_id=pedido.id,
                tipo_orden="domicilio",
                direccion_entrega=
                    "Calle Precision 123",
            )

        pedido.refresh_from_db()

        self.assertEqual(
            pedido.tipo_orden,
            "",
        )

    def test_08_defensa_final_bloquea_total_restaurante_incompatible(self):

        producto = self.crear_producto(
            precio="10.0050",
        )

        pedido = self.crear_pedido()

        # La ruta legacy conserva 4 decimales.
        agregar_producto_a_pedido(
            pedido_id=pedido.id,
            producto_id=producto.id,
            cantidad="1.0000",
        )

        # Simula un dato llegado por otra vía administrativa.
        pedido.tipo_orden = "comedor"

        pedido.save(
            update_fields=[
                "tipo_orden",
                "actualizado_en",
            ]
        )

        with self.assertRaisesMessage(
            ValidationError,
            "subtotal del pedido",
        ):
            confirmar_pedido(
                pedido_id=pedido.id,
            )

        pedido.refresh_from_db()

        self.assertEqual(
            pedido.estado,
            "carrito",
        )

    def test_09_valores_xx_xx00_aceptados(self):

        producto = self.crear_producto(
            precio="19.9900",
        )

        pedido = self.crear_pedido()

        detalle = (
            agregar_producto_configurado_a_pedido(
                pedido_id=pedido.id,
                producto_id=producto.id,
                cantidad="2.0000",
                seleccion_opciones=[],
            )
        )

        pedido = configurar_logistica_pedido(
            pedido_id=pedido.id,
            tipo_orden="comedor",
        )

        self.assertEqual(
            detalle.precio_unitario,
            Decimal("19.9900"),
        )

        self.assertEqual(
            pedido.total,
            Decimal("39.9800"),
        )

    def test_10_legacy_cuatro_decimales_sigue_funcionando(self):

        producto = self.crear_producto(
            precio="1499.4321",
        )

        pedido = self.crear_pedido()

        agregar_producto_a_pedido(
            pedido_id=pedido.id,
            producto_id=producto.id,
            cantidad="1.0000",
        )

        pedido = confirmar_pedido(
            pedido_id=pedido.id,
        )

        self.assertEqual(
            pedido.estado,
            "confirmado",
        )

        self.assertEqual(
            pedido.total,
            Decimal("1499.4321"),
        )
