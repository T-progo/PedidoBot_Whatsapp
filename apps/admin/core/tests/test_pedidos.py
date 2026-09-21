from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import (
    Empresa,
    Bot,
    Canal,
    Catalogo,
    Producto,
    Pedido,
    PedidoDetalle,
)

from core.services.pedidos import (
    crear_pedido,
    agregar_producto_a_pedido,
    confirmar_pedido,
)


class PedidoServiceTests(TestCase):

    def setUp(self):

        # ====================================================
        # EMPRESA PRINCIPAL
        # ====================================================

        self.empresa = Empresa.objects.create(
            nombre="Empresa TEST",
            rfc="TST010101AA1",
        )

        self.bot = Bot.objects.create(
            empresa=self.empresa,
            nombre="Bot TEST",
        )

        self.canal = Canal.objects.create(
            bot=self.bot,
            tipo="whatsapp",
            nombre="WhatsApp TEST",
            identificador="whatsapp-test-001",
            activo=True,
        )

        self.catalogo = Catalogo.objects.create(
            empresa=self.empresa,
            nombre="Catalogo TEST USD",
            descripcion="Catalogo utilizado por pruebas automatizadas.",
            moneda="USD",
            identificador_externo="catalogo-test-usd",
            activo=True,
        )

        self.producto = Producto.objects.create(
            catalogo=self.catalogo,
            sku="PROD-TEST-001",
            nombre="Producto TEST 001",
            descripcion="Producto principal de pruebas.",
            precio=Decimal("1499.4321"),
            stock=Decimal("20.0000"),
            unidad="pieza",
            identificador_externo="producto-test-001",
            activo=True,
        )

    # ========================================================
    # HELPERS
    # ========================================================

    def crear_carrito(
        self,
        *,
        moneda="USD",
        empresa=None,
        canal_id=None,
    ):

        empresa = empresa or self.empresa

        return crear_pedido(
            empresa_id=empresa.id,
            moneda=moneda,
            canal_id=canal_id,
            cliente_nombre="Cliente TEST",
            cliente_telefono="3312345678",
            cliente_email="cliente@test.local",
            direccion_entrega="Direccion TEST",
            notas="Pedido generado por pruebas automatizadas.",
        )

    # ========================================================
    # TEST 01
    # ========================================================

    def test_01_crear_carrito(self):

        pedido = self.crear_carrito()

        self.assertEqual(
            pedido.numero,
            "PED-000001",
        )

        self.assertEqual(
            pedido.estado,
            "carrito",
        )

        self.assertEqual(
            pedido.empresa_id,
            self.empresa.id,
        )

        self.assertEqual(
            pedido.moneda,
            "USD",
        )

        self.assertEqual(
            pedido.subtotal,
            Decimal("0.0000"),
        )

        self.assertEqual(
            pedido.descuento,
            Decimal("0.0000"),
        )

        self.assertEqual(
            pedido.total,
            Decimal("0.0000"),
        )

    # ========================================================
    # TEST 02
    # ========================================================

    def test_02_numeracion_consecutiva(self):

        pedido1 = self.crear_carrito()
        pedido2 = self.crear_carrito()
        pedido3 = self.crear_carrito()

        self.assertEqual(
            pedido1.numero,
            "PED-000001",
        )

        self.assertEqual(
            pedido2.numero,
            "PED-000002",
        )

        self.assertEqual(
            pedido3.numero,
            "PED-000003",
        )

    # ========================================================
    # TEST 03
    # ========================================================

    def test_03_snapshot_producto(self):

        pedido = self.crear_carrito()

        detalle = agregar_producto_a_pedido(
            pedido_id=pedido.id,
            producto_id=self.producto.id,
            cantidad="1.0000",
        )

        self.assertEqual(
            detalle.sku,
            "PROD-TEST-001",
        )

        self.assertEqual(
            detalle.nombre_producto,
            "Producto TEST 001",
        )

        self.assertEqual(
            detalle.precio_unitario,
            Decimal("1499.4321"),
        )

        # Cambiamos posteriormente el producto real.
        self.producto.sku = "PROD-MODIFICADO"
        self.producto.nombre = "Producto modificado"
        self.producto.precio = Decimal("9999.9999")

        self.producto.save()

        detalle.refresh_from_db()

        # El pedido debe conservar su snapshot histórico.
        self.assertEqual(
            detalle.sku,
            "PROD-TEST-001",
        )

        self.assertEqual(
            detalle.nombre_producto,
            "Producto TEST 001",
        )

        self.assertEqual(
            detalle.precio_unitario,
            Decimal("1499.4321"),
        )

    # ========================================================
    # TEST 04
    # ========================================================

    def test_04_precision_cuatro_decimales(self):

        pedido = self.crear_carrito()

        detalle = agregar_producto_a_pedido(
            pedido_id=pedido.id,
            producto_id=self.producto.id,
            cantidad="2.5000",
            descuento="100.1234",
        )

        pedido.refresh_from_db()

        self.assertEqual(
            detalle.cantidad,
            Decimal("2.5000"),
        )

        self.assertEqual(
            detalle.precio_unitario,
            Decimal("1499.4321"),
        )

        self.assertEqual(
            pedido.subtotal,
            Decimal("3748.5803"),
        )

        self.assertEqual(
            pedido.descuento,
            Decimal("100.1234"),
        )

        self.assertEqual(
            detalle.importe,
            Decimal("3648.4569"),
        )

        self.assertEqual(
            pedido.total,
            Decimal("3648.4569"),
        )

    # ========================================================
    # TEST 05
    # ========================================================

    def test_05_carrito_no_descuenta_stock(self):

        stock_inicial = self.producto.stock

        pedido = self.crear_carrito()

        agregar_producto_a_pedido(
            pedido_id=pedido.id,
            producto_id=self.producto.id,
            cantidad="5.0000",
        )

        self.producto.refresh_from_db()

        self.assertEqual(
            self.producto.stock,
            stock_inicial,
        )

    # ========================================================
    # TEST 06
    # ========================================================

    def test_06_confirmacion_descuenta_stock(self):

        pedido = self.crear_carrito()

        agregar_producto_a_pedido(
            pedido_id=pedido.id,
            producto_id=self.producto.id,
            cantidad="2.5000",
        )

        pedido = confirmar_pedido(
            pedido_id=pedido.id,
        )

        self.producto.refresh_from_db()

        self.assertEqual(
            pedido.estado,
            "confirmado",
        )

        self.assertIsNotNone(
            pedido.confirmado_en,
        )

        self.assertEqual(
            self.producto.stock,
            Decimal("17.5000"),
        )

    # ========================================================
    # TEST 07
    # ========================================================

    def test_07_doble_confirmacion_bloqueada(self):

        pedido = self.crear_carrito()

        agregar_producto_a_pedido(
            pedido_id=pedido.id,
            producto_id=self.producto.id,
            cantidad="2.0000",
        )

        confirmar_pedido(
            pedido_id=pedido.id,
        )

        stock_despues_primera = (
            Producto.objects
            .get(pk=self.producto.id)
            .stock
        )

        with self.assertRaises(ValidationError):

            confirmar_pedido(
                pedido_id=pedido.id,
            )

        stock_despues_segunda = (
            Producto.objects
            .get(pk=self.producto.id)
            .stock
        )

        self.assertEqual(
            stock_despues_primera,
            stock_despues_segunda,
        )

        self.assertEqual(
            stock_despues_segunda,
            Decimal("18.0000"),
        )

    # ========================================================
    # TEST 08
    # ========================================================

    def test_08_stock_insuficiente_bloqueado(self):

        pedido = self.crear_carrito()

        agregar_producto_a_pedido(
            pedido_id=pedido.id,
            producto_id=self.producto.id,
            cantidad="25.0000",
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Stock insuficiente",
        ):

            confirmar_pedido(
                pedido_id=pedido.id,
            )

        pedido.refresh_from_db()

        self.assertEqual(
            pedido.estado,
            "carrito",
        )

        self.assertIsNone(
            pedido.confirmado_en,
        )

    # ========================================================
    # TEST 09
    # ========================================================

    def test_09_rollback_conserva_inventario(self):

        stock_inicial = self.producto.stock

        pedido = self.crear_carrito()

        agregar_producto_a_pedido(
            pedido_id=pedido.id,
            producto_id=self.producto.id,
            cantidad="100.0000",
        )

        try:

            confirmar_pedido(
                pedido_id=pedido.id,
            )

        except ValidationError:
            pass

        self.producto.refresh_from_db()
        pedido.refresh_from_db()

        self.assertEqual(
            self.producto.stock,
            stock_inicial,
        )

        self.assertEqual(
            pedido.estado,
            "carrito",
        )

        self.assertIsNone(
            pedido.confirmado_en,
        )

    # ========================================================
    # TEST 10
    # ========================================================

    def test_10_atomicidad_multiproducto(self):

        producto2 = Producto.objects.create(
            catalogo=self.catalogo,
            sku="PROD-TEST-002",
            nombre="Producto TEST 002",
            precio=Decimal("250.1250"),
            stock=Decimal("10.0000"),
            unidad="pieza",
            activo=True,
        )

        pedido = self.crear_carrito()

        # Producto 1 NO tiene stock suficiente.
        agregar_producto_a_pedido(
            pedido_id=pedido.id,
            producto_id=self.producto.id,
            cantidad="25.0000",
        )

        # Producto 2 SI tiene stock suficiente.
        agregar_producto_a_pedido(
            pedido_id=pedido.id,
            producto_id=producto2.id,
            cantidad="2.0000",
        )

        with self.assertRaises(ValidationError):

            confirmar_pedido(
                pedido_id=pedido.id,
            )

        self.producto.refresh_from_db()
        producto2.refresh_from_db()
        pedido.refresh_from_db()

        self.assertEqual(
            self.producto.stock,
            Decimal("20.0000"),
        )

        self.assertEqual(
            producto2.stock,
            Decimal("10.0000"),
        )

        self.assertEqual(
            pedido.estado,
            "carrito",
        )

    # ========================================================
    # TEST 11
    # ========================================================

    def test_11_cantidad_cero_o_negativa_rechazada(self):

        pedido = self.crear_carrito()

        for cantidad in [
            "0.0000",
            "-1.0000",
        ]:

            with self.assertRaisesMessage(
                ValidationError,
                "La cantidad debe ser mayor que cero.",
            ):

                agregar_producto_a_pedido(
                    pedido_id=pedido.id,
                    producto_id=self.producto.id,
                    cantidad=cantidad,
                )

        self.assertEqual(
            PedidoDetalle.objects.count(),
            0,
        )

    # ========================================================
    # TEST 12
    # ========================================================

    def test_12_descuento_negativo_rechazado(self):

        pedido = self.crear_carrito()

        with self.assertRaisesMessage(
            ValidationError,
            "El descuento no puede ser negativo.",
        ):

            agregar_producto_a_pedido(
                pedido_id=pedido.id,
                producto_id=self.producto.id,
                cantidad="1.0000",
                descuento="-0.0001",
            )

        self.assertEqual(
            PedidoDetalle.objects.count(),
            0,
        )

    # ========================================================
    # TEST 13
    # ========================================================

    def test_13_descuento_mayor_bruto_rechazado(self):

        pedido = self.crear_carrito()

        with self.assertRaisesMessage(
            ValidationError,
            "El descuento no puede ser mayor",
        ):

            agregar_producto_a_pedido(
                pedido_id=pedido.id,
                producto_id=self.producto.id,
                cantidad="1.0000",
                descuento="2000.0000",
            )

        self.assertEqual(
            PedidoDetalle.objects.count(),
            0,
        )

    # ========================================================
    # TEST 14
    # ========================================================

    def test_14_producto_otra_empresa_rechazado(self):

        empresa2 = Empresa.objects.create(
            nombre="Empresa TEST 2",
            rfc="TST020202BB2",
        )

        catalogo2 = Catalogo.objects.create(
            empresa=empresa2,
            nombre="Catalogo Empresa 2",
            moneda="USD",
            activo=True,
        )

        producto2 = Producto.objects.create(
            catalogo=catalogo2,
            sku="PROD-EMPRESA-2",
            nombre="Producto Empresa 2",
            precio=Decimal("100.0000"),
            stock=Decimal("10.0000"),
            activo=True,
        )

        pedido = self.crear_carrito()

        with self.assertRaisesMessage(
            ValidationError,
            "no pertenece a la empresa del pedido",
        ):

            agregar_producto_a_pedido(
                pedido_id=pedido.id,
                producto_id=producto2.id,
                cantidad="1.0000",
            )

    # ========================================================
    # TEST 15
    # ========================================================

    def test_15_moneda_incompatible_rechazada(self):

        pedido = self.crear_carrito(
            moneda="MXN",
        )

        with self.assertRaisesMessage(
            ValidationError,
            "La moneda del producto no coincide",
        ):

            agregar_producto_a_pedido(
                pedido_id=pedido.id,
                producto_id=self.producto.id,
                cantidad="1.0000",
            )

    # ========================================================
    # TEST 16
    # ========================================================

    def test_16_producto_inactivo_rechazado(self):

        self.producto.activo = False
        self.producto.save(
            update_fields=[
                "activo",
            ]
        )

        pedido = self.crear_carrito()

        with self.assertRaisesMessage(
            ValidationError,
            "El producto seleccionado está inactivo.",
        ):

            agregar_producto_a_pedido(
                pedido_id=pedido.id,
                producto_id=self.producto.id,
                cantidad="1.0000",
            )

    # ========================================================
    # TEST 17
    # ========================================================

    def test_17_catalogo_inactivo_rechazado(self):

        self.catalogo.activo = False
        self.catalogo.save(
            update_fields=[
                "activo",
            ]
        )

        pedido = self.crear_carrito()

        with self.assertRaisesMessage(
            ValidationError,
            "El catálogo del producto está inactivo.",
        ):

            agregar_producto_a_pedido(
                pedido_id=pedido.id,
                producto_id=self.producto.id,
                cantidad="1.0000",
            )

    # ========================================================
    # TEST 18
    # ========================================================

    def test_18_pedido_vacio_no_confirmable(self):

        pedido = self.crear_carrito()

        with self.assertRaisesMessage(
            ValidationError,
            "No se puede confirmar un pedido sin productos.",
        ):

            confirmar_pedido(
                pedido_id=pedido.id,
            )

        pedido.refresh_from_db()

        self.assertEqual(
            pedido.estado,
            "carrito",
        )

        self.assertIsNone(
            pedido.confirmado_en,
        )
