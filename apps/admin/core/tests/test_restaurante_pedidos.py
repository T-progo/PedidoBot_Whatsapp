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
    actualizar_detalle_pedido,
    configurar_logistica_pedido,
    recalcular_pedido,
)


class RestaurantePedidoServiceTests(TestCase):

    def setUp(self):

        self.empresa = Empresa.objects.create(
            nombre="Restaurante TEST",
            rfc="RST010101AA1",
        )

        self.catalogo = Catalogo.objects.create(
            empresa=self.empresa,
            nombre="Menu TEST",
            moneda="MXN",
            activo=True,
        )

        self.producto = Producto.objects.create(
            catalogo=self.catalogo,
            sku="REST-001",
            nombre="Hamburguesa TEST",
            precio=Decimal("100.0000"),
            stock=Decimal("100.0000"),
            activo=True,
        )

        self.config = (
            ConfiguracionRestaurante.objects.create(
                empresa=self.empresa,
                costo_envio_fijo=Decimal("35.0000"),
                envio_gratis_desde=Decimal("300.0000"),
                tiempo_estimado_minutos=25,
                habilitada=True,
            )
        )

        self.grupo_tamano = (
            GrupoModificadorProducto.objects.create(
                producto=self.producto,
                nombre="Tamaño",
                tipo=(
                    GrupoModificadorProducto
                    .Tipo
                    .MODIFICADOR
                ),
                obligatorio=True,
                minimo=1,
                maximo=1,
                orden=1,
                activo=True,
            )
        )

        self.op_grande = (
            OpcionModificadorProducto.objects.create(
                grupo=self.grupo_tamano,
                nombre="Grande",
                precio_adicional=Decimal("20.0000"),
                orden=1,
                activa=True,
            )
        )

        self.grupo_extras = (
            GrupoModificadorProducto.objects.create(
                producto=self.producto,
                nombre="Extras",
                tipo=(
                    GrupoModificadorProducto
                    .Tipo
                    .EXTRA
                ),
                obligatorio=False,
                minimo=0,
                maximo=2,
                orden=2,
                activo=True,
            )
        )

        self.op_queso = (
            OpcionModificadorProducto.objects.create(
                grupo=self.grupo_extras,
                nombre="Queso",
                precio_adicional=Decimal("10.5000"),
                orden=1,
                activa=True,
            )
        )

        self.op_tocino = (
            OpcionModificadorProducto.objects.create(
                grupo=self.grupo_extras,
                nombre="Tocino",
                precio_adicional=Decimal("15.2500"),
                orden=2,
                activa=True,
            )
        )

        self.op_aguacate = (
            OpcionModificadorProducto.objects.create(
                grupo=self.grupo_extras,
                nombre="Aguacate",
                precio_adicional=Decimal("12.0000"),
                orden=3,
                activa=True,
            )
        )

    def crear_carrito(self):
        return crear_pedido(
            empresa_id=self.empresa.id,
            moneda="MXN",
            cliente_nombre="Cliente TEST",
            cliente_telefono="3312345678",
            cliente_email="cliente@test.local",
            direccion_entrega="",
            notas="",
        )

    def seleccion_completa(self):
        return [
            self.op_grande.id,
            self.op_queso.id,
            self.op_tocino.id,
        ]

    def test_01_precio_configurado_y_snapshot(self):

        pedido = self.crear_carrito()

        detalle = (
            agregar_producto_configurado_a_pedido(
                pedido_id=pedido.id,
                producto_id=self.producto.id,
                cantidad="2.0000",
                seleccion_opciones=
                    self.seleccion_completa(),
            )
        )

        pedido.refresh_from_db()

        self.assertEqual(
            detalle.precio_base,
            Decimal("100.0000"),
        )

        self.assertEqual(
            detalle.precio_modificadores,
            Decimal("20.0000"),
        )

        self.assertEqual(
            detalle.precio_extras,
            Decimal("25.7500"),
        )

        self.assertEqual(
            detalle.precio_unitario,
            Decimal("145.7500"),
        )

        self.assertEqual(
            detalle.importe,
            Decimal("291.5000"),
        )

        self.assertEqual(
            pedido.subtotal_productos,
            Decimal("200.0000"),
        )

        self.assertEqual(
            pedido.subtotal_modificadores,
            Decimal("40.0000"),
        )

        self.assertEqual(
            pedido.subtotal_extras,
            Decimal("51.5000"),
        )

        self.assertEqual(
            pedido.subtotal,
            Decimal("291.5000"),
        )

        self.assertEqual(
            pedido.total,
            Decimal("291.5000"),
        )

        self.assertEqual(
            len(detalle.modificadores_snapshot),
            1,
        )

        self.assertEqual(
            len(detalle.extras_snapshot),
            1,
        )

    def test_02_modificador_obligatorio(self):

        pedido = self.crear_carrito()

        with self.assertRaisesMessage(
            ValidationError,
            "requiere al menos 1",
        ):
            agregar_producto_configurado_a_pedido(
                pedido_id=pedido.id,
                producto_id=self.producto.id,
                cantidad="1.0000",
                seleccion_opciones=[],
            )

        self.assertEqual(
            PedidoDetalle.objects.count(),
            0,
        )

    def test_03_maximo_extras(self):

        pedido = self.crear_carrito()

        with self.assertRaisesMessage(
            ValidationError,
            "permite máximo 2",
        ):
            agregar_producto_configurado_a_pedido(
                pedido_id=pedido.id,
                producto_id=self.producto.id,
                cantidad="1.0000",
                seleccion_opciones=[
                    self.op_grande.id,
                    self.op_queso.id,
                    self.op_tocino.id,
                    self.op_aguacate.id,
                ],
            )

    def test_04_opcion_duplicada(self):

        pedido = self.crear_carrito()

        with self.assertRaisesMessage(
            ValidationError,
            "dos veces la misma opción",
        ):
            agregar_producto_configurado_a_pedido(
                pedido_id=pedido.id,
                producto_id=self.producto.id,
                cantidad="1.0000",
                seleccion_opciones=[
                    self.op_grande.id,
                    self.op_grande.id,
                ],
            )

    def test_05_opcion_inactiva(self):

        self.op_grande.activa = False
        self.op_grande.save(
            update_fields=[
                "activa",
            ]
        )

        pedido = self.crear_carrito()

        with self.assertRaisesMessage(
            ValidationError,
            "no existen o están inactivas",
        ):
            agregar_producto_configurado_a_pedido(
                pedido_id=pedido.id,
                producto_id=self.producto.id,
                cantidad="1.0000",
                seleccion_opciones=[
                    self.op_grande.id,
                ],
            )

    def test_06_opcion_otro_producto(self):

        otro = Producto.objects.create(
            catalogo=self.catalogo,
            nombre="Otro producto",
            precio=Decimal("50.0000"),
            stock=Decimal("10.0000"),
            activo=True,
        )

        grupo = (
            GrupoModificadorProducto.objects.create(
                producto=otro,
                nombre="Otro grupo",
                obligatorio=False,
                minimo=0,
                maximo=1,
                activo=True,
            )
        )

        opcion = (
            OpcionModificadorProducto.objects.create(
                grupo=grupo,
                nombre="Otra opción",
                precio_adicional=Decimal("5.0000"),
                activa=True,
            )
        )

        pedido = self.crear_carrito()

        with self.assertRaisesMessage(
            ValidationError,
            "no pertenece al producto",
        ):
            agregar_producto_configurado_a_pedido(
                pedido_id=pedido.id,
                producto_id=self.producto.id,
                cantidad="1.0000",
                seleccion_opciones=[
                    self.op_grande.id,
                    opcion.id,
                ],
            )

    def test_07_comedor_sin_envio(self):

        pedido = self.crear_carrito()

        agregar_producto_configurado_a_pedido(
            pedido_id=pedido.id,
            producto_id=self.producto.id,
            cantidad="2.0000",
            seleccion_opciones=
                self.seleccion_completa(),
        )

        pedido = configurar_logistica_pedido(
            pedido_id=pedido.id,
            tipo_orden="comedor",
        )

        self.assertEqual(
            pedido.tipo_orden,
            "comedor",
        )

        self.assertEqual(
            pedido.costo_envio,
            Decimal("0.0000"),
        )

        self.assertEqual(
            pedido.direccion_entrega,
            "",
        )

        self.assertEqual(
            pedido.total,
            Decimal("291.5000"),
        )

        self.assertEqual(
            pedido.tiempo_estimado_minutos,
            25,
        )

    def test_08_para_llevar_sin_envio(self):

        pedido = self.crear_carrito()

        agregar_producto_configurado_a_pedido(
            pedido_id=pedido.id,
            producto_id=self.producto.id,
            cantidad="2.0000",
            seleccion_opciones=
                self.seleccion_completa(),
        )

        pedido = configurar_logistica_pedido(
            pedido_id=pedido.id,
            tipo_orden="para_llevar",
        )

        self.assertEqual(
            pedido.costo_envio,
            Decimal("0.0000"),
        )

        self.assertEqual(
            pedido.total,
            Decimal("291.5000"),
        )

    def test_09_domicilio_con_envio_fijo(self):

        pedido = self.crear_carrito()

        agregar_producto_configurado_a_pedido(
            pedido_id=pedido.id,
            producto_id=self.producto.id,
            cantidad="2.0000",
            seleccion_opciones=
                self.seleccion_completa(),
        )

        pedido = configurar_logistica_pedido(
            pedido_id=pedido.id,
            tipo_orden="domicilio",
            direccion_entrega=
                "Calle TEST 123",
        )

        self.assertEqual(
            pedido.costo_envio,
            Decimal("35.0000"),
        )

        self.assertEqual(
            pedido.total,
            Decimal("326.5000"),
        )

    def test_10_envio_gratis_umbral(self):

        pedido = self.crear_carrito()

        agregar_producto_configurado_a_pedido(
            pedido_id=pedido.id,
            producto_id=self.producto.id,
            cantidad="3.0000",
            seleccion_opciones=
                self.seleccion_completa(),
        )

        pedido = configurar_logistica_pedido(
            pedido_id=pedido.id,
            tipo_orden="domicilio",
            direccion_entrega=
                "Calle TEST 123",
        )

        self.assertEqual(
            pedido.subtotal,
            Decimal("437.2500"),
        )

        self.assertEqual(
            pedido.costo_envio,
            Decimal("0.0000"),
        )

        self.assertEqual(
            pedido.total,
            Decimal("437.2500"),
        )

    def test_11_descuento_y_envio(self):

        pedido = self.crear_carrito()

        agregar_producto_configurado_a_pedido(
            pedido_id=pedido.id,
            producto_id=self.producto.id,
            cantidad="2.0000",
            seleccion_opciones=
                self.seleccion_completa(),
            descuento="5.0000",
        )

        pedido = configurar_logistica_pedido(
            pedido_id=pedido.id,
            tipo_orden="domicilio",
            direccion_entrega=
                "Calle TEST 123",
        )

        self.assertEqual(
            pedido.subtotal,
            Decimal("291.5000"),
        )

        self.assertEqual(
            pedido.descuento,
            Decimal("5.0000"),
        )

        self.assertEqual(
            pedido.costo_envio,
            Decimal("35.0000"),
        )

        self.assertEqual(
            pedido.total,
            Decimal("321.5000"),
        )

    def test_12_cambiar_cantidad_recalcula_envio(self):

        pedido = self.crear_carrito()

        detalle = (
            agregar_producto_configurado_a_pedido(
                pedido_id=pedido.id,
                producto_id=self.producto.id,
                cantidad="2.0000",
                seleccion_opciones=
                    self.seleccion_completa(),
            )
        )

        configurar_logistica_pedido(
            pedido_id=pedido.id,
            tipo_orden="domicilio",
            direccion_entrega=
                "Calle TEST 123",
        )

        actualizar_detalle_pedido(
            detalle_id=detalle.id,
            cantidad="3.0000",
        )

        pedido.refresh_from_db()

        self.assertEqual(
            pedido.subtotal,
            Decimal("437.2500"),
        )

        self.assertEqual(
            pedido.costo_envio,
            Decimal("0.0000"),
        )

        self.assertEqual(
            pedido.total,
            Decimal("437.2500"),
        )

    def test_13_legacy_precio_base_null_compatible(self):

        pedido = self.crear_carrito()

        detalle = agregar_producto_a_pedido(
            pedido_id=pedido.id,
            producto_id=self.producto.id,
            cantidad="2.0000",
        )

        detalle.refresh_from_db()

        self.assertIsNone(
            detalle.precio_base
        )

        pedido = recalcular_pedido(
            pedido.id
        )

        self.assertEqual(
            pedido.subtotal_productos,
            Decimal("200.0000"),
        )

        self.assertEqual(
            pedido.subtotal_modificadores,
            Decimal("0.0000"),
        )

        self.assertEqual(
            pedido.subtotal_extras,
            Decimal("0.0000"),
        )

        self.assertEqual(
            pedido.total,
            Decimal("200.0000"),
        )

    def test_14_domicilio_requiere_direccion(self):

        pedido = self.crear_carrito()

        agregar_producto_configurado_a_pedido(
            pedido_id=pedido.id,
            producto_id=self.producto.id,
            cantidad="1.0000",
            seleccion_opciones=[
                self.op_grande.id,
            ],
        )

        with self.assertRaisesMessage(
            ValidationError,
            "dirección de entrega",
        ):
            configurar_logistica_pedido(
                pedido_id=pedido.id,
                tipo_orden="domicilio",
            )

    def test_15_restaurante_requiere_configuracion(self):

        empresa2 = Empresa.objects.create(
            nombre="Restaurante sin config",
            rfc="RST020202BB2",
        )

        catalogo2 = Catalogo.objects.create(
            empresa=empresa2,
            nombre="Menu sin config",
            moneda="MXN",
            activo=True,
        )

        producto2 = Producto.objects.create(
            catalogo=catalogo2,
            nombre="Producto simple",
            precio=Decimal("50.0000"),
            stock=Decimal("10.0000"),
            activo=True,
        )

        pedido = crear_pedido(
            empresa_id=empresa2.id,
            moneda="MXN",
        )

        agregar_producto_a_pedido(
            pedido_id=pedido.id,
            producto_id=producto2.id,
            cantidad="1.0000",
        )

        with self.assertRaisesMessage(
            ValidationError,
            "configuración activa",
        ):
            configurar_logistica_pedido(
                pedido_id=pedido.id,
                tipo_orden="comedor",
            )

    def test_16_varios_extras_una_sola_vez(self):
        """
        Varios extras en una línea: cada opción se guarda y
        se cobra una sola vez (bucle de extras de Typebot).
        """


        pedido = self.crear_carrito()

        detalle = (
            agregar_producto_configurado_a_pedido(
                pedido_id=pedido.id,
                producto_id=self.producto.id,
                cantidad="1.0000",
                seleccion_opciones=[
                    self.op_grande.id,
                    self.op_queso.id,
                    self.op_tocino.id,
                ],
            )
        )

        opcion_ids = [
            opcion["opcion_id"]
            for grupo in (
                list(detalle.modificadores_snapshot)
                + list(detalle.extras_snapshot)
            )
            for opcion in grupo["opciones"]
        ]

        self.assertEqual(
            sorted(opcion_ids),
            sorted(
                [
                    self.op_grande.id,
                    self.op_queso.id,
                    self.op_tocino.id,
                ]
            ),
        )

        self.assertEqual(
            len(opcion_ids),
            len(set(opcion_ids)),
        )

        self.assertEqual(
            detalle.precio_extras,
            Decimal("25.7500"),
        )

        self.assertEqual(
            detalle.precio_unitario,
            Decimal("145.7500"),
        )

    def test_17_extra_repetido_no_cobra_doble(self):

        pedido = self.crear_carrito()

        with self.assertRaisesMessage(
            ValidationError,
            "dos veces la misma opción",
        ):
            agregar_producto_configurado_a_pedido(
                pedido_id=pedido.id,
                producto_id=self.producto.id,
                cantidad="1.0000",
                seleccion_opciones=[
                    self.op_grande.id,
                    self.op_queso.id,
                    self.op_queso.id,
                ],
            )

        self.assertEqual(
            PedidoDetalle.objects.count(),
            0,
        )
