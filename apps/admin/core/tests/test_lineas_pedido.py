"""
Representación de líneas con modificadores y extras.

TNL-LINEAS-PEDIDO-V1: el texto se arma desde los snapshots
guardados en la línea; los totales no se tocan.
"""

from decimal import Decimal

from django.test import TestCase

from core.models import (
    Catalogo,
    ConfiguracionRestaurante,
    Empresa,
    GrupoModificadorProducto,
    OpcionModificadorProducto,
    Producto,
)
from core.services.lineas_pedido import (
    describir_detalle,
    describir_linea,
    texto_linea,
    texto_lineas,
)
from core.services.pedidos import (
    agregar_producto_a_pedido,
    agregar_producto_configurado_a_pedido,
    crear_pedido,
)
from core.views_api import _restaurante_api_construir_resumen_texto


class LineasPedidoTests(TestCase):

    def setUp(self):

        self.empresa = Empresa.objects.create(
            nombre="Restaurante LINEAS",
            rfc="RLN010101AA1",
        )

        self.catalogo = Catalogo.objects.create(
            empresa=self.empresa,
            nombre="Menu LINEAS",
            moneda="MXN",
            activo=True,
        )

        ConfiguracionRestaurante.objects.create(
            empresa=self.empresa,
            costo_envio_fijo=Decimal("0.0000"),
            envio_gratis_desde=Decimal("0.0000"),
            tiempo_estimado_minutos=20,
            habilitada=True,
        )

        self.alitas = Producto.objects.create(
            catalogo=self.catalogo,
            sku="LIN-001",
            nombre="Alitas",
            precio=Decimal("10.0000"),
            stock=Decimal("50.0000"),
            activo=True,
        )

        self.refresco = Producto.objects.create(
            catalogo=self.catalogo,
            sku="LIN-002",
            nombre="Refresco",
            precio=Decimal("20.0000"),
            stock=Decimal("50.0000"),
            activo=True,
        )

        self.grupo_salsa = (
            GrupoModificadorProducto.objects.create(
                producto=self.alitas,
                nombre="Salsa",
                tipo=GrupoModificadorProducto.Tipo.MODIFICADOR,
                obligatorio=True,
                minimo=1,
                maximo=1,
                orden=1,
                activo=True,
            )
        )

        self.bbq = OpcionModificadorProducto.objects.create(
            grupo=self.grupo_salsa,
            nombre="BBQ",
            precio_adicional=Decimal("0.0000"),
            orden=1,
            activa=True,
        )

        self.grupo_extras = (
            GrupoModificadorProducto.objects.create(
                producto=self.alitas,
                nombre="Extras",
                tipo=GrupoModificadorProducto.Tipo.EXTRA,
                obligatorio=False,
                minimo=0,
                maximo=3,
                orden=2,
                activo=True,
            )
        )

        self.buffalo = OpcionModificadorProducto.objects.create(
            grupo=self.grupo_extras,
            nombre="Buffalo hot",
            precio_adicional=Decimal("5.0000"),
            orden=1,
            activa=True,
        )

        self.teriyaki = OpcionModificadorProducto.objects.create(
            grupo=self.grupo_extras,
            nombre="Teriyaki",
            precio_adicional=Decimal("5.0000"),
            orden=2,
            activa=True,
        )

    def crear_carrito(self):
        return crear_pedido(
            empresa_id=self.empresa.id,
            moneda="MXN",
            cliente_nombre="Cliente LINEAS",
            cliente_telefono="3312345678",
            cliente_email="",
            direccion_entrega="",
            notas="",
        )

    def test_01_linea_sin_modificadores(self):

        pedido = self.crear_carrito()

        detalle = agregar_producto_a_pedido(
            pedido_id=pedido.id,
            producto_id=self.refresco.id,
            cantidad="2.0000",
        )

        descripcion = describir_detalle(detalle)

        self.assertEqual(descripcion["grupos"], [])

        self.assertEqual(
            texto_linea(descripcion, prefijo="1. "),
            "1. Refresco x2 — $40.00",
        )

    def test_02_modificador_obligatorio_y_varios_extras(self):

        pedido = self.crear_carrito()

        detalle = agregar_producto_configurado_a_pedido(
            pedido_id=pedido.id,
            producto_id=self.alitas.id,
            cantidad="2.0000",
            seleccion_opciones=[
                self.bbq.id,
                self.buffalo.id,
                self.teriyaki.id,
            ],
        )

        texto = texto_linea(
            describir_detalle(detalle),
            prefijo="1. ",
        )

        self.assertEqual(
            texto,
            "1. Alitas x2 — $40.00\n"
            "   Salsa: BBQ\n"
            "   Extras: Buffalo hot, Teriyaki",
        )

    def test_03_nombres_y_precios_vienen_del_snapshot(self):

        pedido = self.crear_carrito()

        detalle = agregar_producto_configurado_a_pedido(
            pedido_id=pedido.id,
            producto_id=self.alitas.id,
            cantidad="1.0000",
            seleccion_opciones=[
                self.bbq.id,
                self.buffalo.id,
            ],
        )

        # El catálogo cambia después de guardar la línea.
        self.buffalo.nombre = "Buffalo NUEVO"
        self.buffalo.precio_adicional = Decimal("99.0000")
        self.buffalo.save(
            update_fields=[
                "nombre",
                "precio_adicional",
            ]
        )

        descripcion = describir_detalle(detalle)

        extras = descripcion["grupos"][1]

        self.assertEqual(
            extras["opciones"][0]["nombre"],
            "Buffalo hot",
        )

        self.assertEqual(
            extras["opciones"][0]["precio_adicional"],
            "5.0000",
        )

    def test_04_snapshot_incompleto_no_rompe(self):

        descripcion = describir_linea(
            nombre="Producto raro",
            cantidad="1.0000",
            importe="10.00",
            modificadores=[
                {"grupo_nombre": "Sin opciones"},
                "basura",
                {"opciones": [{"nombre": "Suelta"}]},
            ],
            extras=None,
        )

        self.assertEqual(
            texto_linea(descripcion),
            "Producto raro x1 — $10.00\n   Opciones: Suelta",
        )

    def test_05_resumen_conserva_totales(self):

        payload = {
            "pedido_numero": "PED-000123",
            "moneda": "MXN",
            "tipo_orden": "para_llevar",
            "subtotal_productos": "20.00",
            "subtotal_modificadores": "0.00",
            "subtotal_extras": "10.00",
            "costo_envio": "0.00",
            "descuento": "0.00",
            "total": "30.00",
            "lineas": [
                {
                    "nombre": "Alitas",
                    "cantidad": "2.0000",
                    "importe": "30.00",
                    "modificadores": [
                        {
                            "tipo": "modificador",
                            "grupo_nombre": "Salsa",
                            "opciones": [
                                {
                                    "opcion_id": 1,
                                    "nombre": "BBQ",
                                    "precio_adicional": "0.0000",
                                },
                            ],
                        },
                    ],
                    "extras": [
                        {
                            "tipo": "extra",
                            "grupo_nombre": "Extras",
                            "opciones": [
                                {
                                    "opcion_id": 2,
                                    "nombre": "Buffalo hot",
                                    "precio_adicional": "5.0000",
                                },
                                {
                                    "opcion_id": 3,
                                    "nombre": "Teriyaki",
                                    "precio_adicional": "5.0000",
                                },
                            ],
                        },
                    ],
                },
            ],
        }

        texto = _restaurante_api_construir_resumen_texto(payload)

        self.assertIn(
            "1. Alitas x2 — $30.00\n"
            "   Salsa: BBQ\n"
            "   Extras: Buffalo hot, Teriyaki",
            texto,
        )

        for esperado in (
            "Productos: $20.00",
            "Modificadores: $0.00",
            "Extras: $10.00",
            "Envío: $0.00",
            "Descuento: $0.00",
            "TOTAL: $30.00 MXN",
        ):
            self.assertIn(esperado, texto)

    def test_06_resumen_sin_productos(self):

        texto = _restaurante_api_construir_resumen_texto(
            {
                "pedido_numero": "PED-000124",
                "lineas": [],
                "total": "0.00",
            }
        )

        self.assertIn("Sin productos.", texto)

    def test_07_lista_para_consulta_sin_importes(self):

        pedido = self.crear_carrito()

        primera = agregar_producto_configurado_a_pedido(
            pedido_id=pedido.id,
            producto_id=self.alitas.id,
            cantidad="1.0000",
            seleccion_opciones=[
                self.bbq.id,
                self.teriyaki.id,
            ],
        )

        segunda = agregar_producto_a_pedido(
            pedido_id=pedido.id,
            producto_id=self.refresco.id,
            cantidad="1.0000",
        )

        texto = texto_lineas(
            [
                describir_detalle(primera),
                describir_detalle(segunda),
            ],
            numerar=False,
            con_importe=False,
        )

        self.assertEqual(
            texto,
            "• Alitas x1\n"
            "   Salsa: BBQ\n"
            "   Extras: Teriyaki\n"
            "• Refresco x1",
        )
