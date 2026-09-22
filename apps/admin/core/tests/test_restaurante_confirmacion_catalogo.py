import json
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from core.models import (
    Bot,
    Catalogo,
    CategoriaProducto,
    ConfiguracionRestaurante,
    Empresa,
    GrupoModificadorProducto,
    OpcionModificadorProducto,
    Pago,
    Pedido,
    Plantilla,
    Producto,
)
from core.services.pedidos import (
    agregar_producto_a_pedido,
    confirmar_pedido,
    crear_pedido,
    texto_aviso_ajuste_precios,
)


# TNL-RESTAURANTE-CONFIRMACION-CATALOGO-V1
# TNL-RESTAURANTE-DISPONIBILIDAD-V1
class ConfirmacionCatalogoRestauranteTests(TestCase):

    def setUp(self):
        key = patch("core.views_api._leer_clave_api", return_value="confirmacion-test-key")
        vida = patch("core.views_api._nl_api_empresa_operativa_error", return_value=None)
        key.start()
        vida.start()
        self.addCleanup(key.stop)
        self.addCleanup(vida.stop)
        self.auth = {"HTTP_AUTHORIZATION": "Bearer confirmacion-test-key"}

        self.empresa = Empresa.objects.create(nombre="Burgers Centro", rfc="BCE010101AA1")
        self.plantilla = Plantilla.objects.create(
            empresa=self.empresa, nombre="Restaurante", tipo="restaurante", activa=True,
        )
        self.bot = Bot.objects.create(empresa=self.empresa, plantilla=self.plantilla, nombre="Bot", activo=True)
        self.catalogo = Catalogo.objects.create(
            empresa=self.empresa, plantilla=self.plantilla, nombre="Menú", moneda="MXN", activo=True,
        )
        self.categoria = CategoriaProducto.objects.create(catalogo=self.catalogo, nombre="Burgers", activa=True)
        ConfiguracionRestaurante.objects.create(
            empresa=self.empresa, costo_envio_fijo=Decimal("0"), tiempo_estimado_minutos=20, habilitada=True,
        )
        # Stock numérico bajo a propósito: en restaurante no debe contar.
        self.producto = Producto.objects.create(
            catalogo=self.catalogo, categoria=self.categoria, sku="BUR-1", nombre="Hamburguesa",
            precio=Decimal("100.00"), stock=Decimal("1"), unidad="pieza", activo=True,
        )
        self.tamano = GrupoModificadorProducto.objects.create(
            producto=self.producto, nombre="Tamaño", tipo="modificador", obligatorio=True, minimo=1, maximo=1,
        )
        self.grande = OpcionModificadorProducto.objects.create(
            grupo=self.tamano, nombre="Grande", precio_adicional=Decimal("20.00"),
        )
        self.extras = GrupoModificadorProducto.objects.create(
            producto=self.producto, nombre="Extras", tipo="extra", obligatorio=False, minimo=0, maximo=2,
        )
        self.queso = OpcionModificadorProducto.objects.create(
            grupo=self.extras, nombre="Queso", precio_adicional=Decimal("10.00"),
        )

    # --- utilidades ----------------------------------------------------------

    def post(self, name, payload):
        return self.client.post(
            reverse(f"core:{name}"), data=json.dumps(payload), content_type="application/json", **self.auth,
        )

    def armar_carrito(self, cantidad="3", opcion_ids=None):
        """Carrito listo para confirmar: 3 x (100 + Grande 20 + Queso 10) = 390."""
        response = self.post("api_typebot_restaurante_pedido_producto_agregar", {
            "bot_id": self.bot.id, "producto_id": self.producto.id, "cantidad": cantidad,
            "opcion_ids": [self.grande.id, self.queso.id] if opcion_ids is None else opcion_ids,
            "suprimir_cross_sell": True,
        })
        self.assertEqual(response.status_code, 200, response.content)
        token = response.json()["carrito_token"]
        self.assertEqual(self.post("api_typebot_restaurante_pedido_datos", {
            "bot_id": self.bot.id, "carrito_token": token,
            "cliente_nombre": "Cliente Prueba", "cliente_telefono": "3300000000",
        }).status_code, 200)
        self.assertEqual(self.post("api_typebot_restaurante_pedido_logistica", {
            "bot_id": self.bot.id, "carrito_token": token, "tipo_orden": "comedor",
        }).status_code, 200)
        return token

    def confirmar(self, token):
        return self.post("api_typebot_restaurante_pedido_confirmar", {"bot_id": self.bot.id, "carrito_token": token})

    def pedido(self):
        return Pedido.objects.get()

    # --- precios ---------------------------------------------------------------

    def test_sin_cambios_no_hay_aviso(self):
        token = self.armar_carrito()
        data = self.confirmar(token).json()
        self.assertTrue(data["pedido_confirmado"])
        self.assertFalse(data["precios_actualizados"])
        self.assertEqual(data["aviso_precios"], "")
        self.assertEqual(data["ajustes_precio"], [])
        self.assertEqual(data["mensaje"], f"Pedido {data['pedido_numero']} confirmado correctamente.")
        self.assertEqual(data["total"], "390.00")

    def test_cambio_precio_producto_se_actualiza_y_avisa(self):
        token = self.armar_carrito()
        Producto.objects.filter(pk=self.producto.pk).update(precio=Decimal("110.00"))
        data = self.confirmar(token).json()

        self.assertTrue(data["pedido_confirmado"])
        self.assertTrue(data["precios_actualizados"])
        # 3 x (110 + 20 + 10) = 420
        self.assertEqual(data["total"], "420.00")
        self.assertEqual(data["ajustes_precio"], [{
            "producto": "Hamburguesa", "cantidad": "3.00",
            "precio_anterior": "130.00", "precio_actual": "140.00",
        }])
        self.assertIn("Cambió el precio de «Hamburguesa» de $130.00 a $140.00.", data["aviso_precios"])
        self.assertIn("Tu total ahora es $420.00 MXN.", data["aviso_precios"])
        # Typebot muestra "mensaje" antes de elegir el pago.
        self.assertTrue(data["mensaje"].endswith(data["aviso_precios"]))

        linea = self.pedido().detalles.get()
        self.assertEqual(linea.precio_base, Decimal("110.00"))
        self.assertEqual(linea.precio_unitario, Decimal("140.00"))
        self.assertEqual(linea.importe, Decimal("420.00"))

    def test_cambio_precio_modificador_y_extra(self):
        token = self.armar_carrito()
        OpcionModificadorProducto.objects.filter(pk=self.grande.pk).update(precio_adicional=Decimal("25.00"))
        OpcionModificadorProducto.objects.filter(pk=self.queso.pk).update(precio_adicional=Decimal("5.00"))
        data = self.confirmar(token).json()

        self.assertTrue(data["pedido_confirmado"])
        # 3 x (100 + 25 + 5) = 390: mismo total, pero el desglose cambia y el
        # precio unitario no, así que no hay aviso.
        self.assertFalse(data["precios_actualizados"])
        pedido = self.pedido()
        self.assertEqual(pedido.subtotal_modificadores, Decimal("75.00"))
        self.assertEqual(pedido.subtotal_extras, Decimal("15.00"))
        self.assertEqual(pedido.total, Decimal("390.00"))
        linea = pedido.detalles.get()
        self.assertEqual(linea.extras_snapshot[0]["opciones"][0]["precio_adicional"], "5.0000")

    def test_cambio_precio_modificador_cambia_total_y_avisa(self):
        token = self.armar_carrito()
        OpcionModificadorProducto.objects.filter(pk=self.grande.pk).update(precio_adicional=Decimal("30.00"))
        data = self.confirmar(token).json()
        self.assertTrue(data["precios_actualizados"])
        # 3 x (100 + 30 + 10) = 420
        self.assertEqual(data["total"], "420.00")
        pedido = self.pedido()
        self.assertEqual(pedido.subtotal_productos + pedido.subtotal_modificadores + pedido.subtotal_extras,
                         pedido.subtotal)
        self.assertEqual(pedido.total, pedido.subtotal + pedido.costo_envio - pedido.descuento)

    def test_pago_usa_el_total_actualizado(self):
        token = self.armar_carrito()
        Producto.objects.filter(pk=self.producto.pk).update(precio=Decimal("110.00"))
        self.assertEqual(self.confirmar(token).json()["total"], "420.00")
        response = self.post("api_typebot_restaurante_pedido_pago_directo", {"bot_id": self.bot.id, "carrito_token": token})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Pago.objects.get().monto, Decimal("420.00"))

    # --- disponibilidad --------------------------------------------------------

    def assert_requiere_revision(self, response, texto):
        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["codigo"], "PEDIDO_REQUIERE_REVISION")
        self.assertIn(texto, data["mensaje"])
        self.assertIn("Revisa tu pedido", data["mensaje"])
        pedido = self.pedido()
        self.assertEqual(pedido.estado, "carrito")
        return pedido

    def test_producto_agotado_no_confirma(self):
        token = self.armar_carrito()
        Producto.objects.filter(pk=self.producto.pk).update(activo=False)
        self.assert_requiere_revision(self.confirmar(token), "«Hamburguesa» ya no está disponible.")

    def test_categoria_desactivada_no_confirma(self):
        token = self.armar_carrito()
        CategoriaProducto.objects.filter(pk=self.categoria.pk).update(activa=False)
        self.assert_requiere_revision(self.confirmar(token), "«Hamburguesa» ya no está disponible.")

    def test_opcion_no_disponible_no_confirma(self):
        token = self.armar_carrito()
        OpcionModificadorProducto.objects.filter(pk=self.queso.pk).update(activa=False)
        self.assert_requiere_revision(
            self.confirmar(token), "«Hamburguesa»: una opción que elegiste ya no está disponible.",
        )

    def test_regla_nueva_de_grupo_no_confirma(self):
        token = self.armar_carrito()
        salsa = GrupoModificadorProducto.objects.create(
            producto=self.producto, nombre="Salsa", obligatorio=True, minimo=1, maximo=1,
        )
        OpcionModificadorProducto.objects.create(grupo=salsa, nombre="BBQ")
        self.assert_requiere_revision(self.confirmar(token), "«Hamburguesa»: El grupo 'Salsa'")

    def test_rechazo_no_guarda_cambios_de_precio(self):
        token = self.armar_carrito()
        Producto.objects.filter(pk=self.producto.pk).update(precio=Decimal("200.00"))
        OpcionModificadorProducto.objects.filter(pk=self.queso.pk).update(activa=False)
        pedido = self.assert_requiere_revision(self.confirmar(token), "ya no está disponible")
        self.assertEqual(pedido.total, Decimal("390.00"))
        self.assertEqual(pedido.detalles.get().precio_base, Decimal("100.00"))

    # --- sin inventario numérico -------------------------------------------------

    def test_cantidad_no_limitada_por_stock_y_stock_intacto(self):
        token = self.armar_carrito(cantidad="5")  # stock numérico = 1
        data = self.confirmar(token).json()
        self.assertTrue(data["pedido_confirmado"], data)
        self.assertEqual(data["total"], "650.00")
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, Decimal("1"))

    def test_producto_con_stock_cero_se_vende(self):
        Producto.objects.filter(pk=self.producto.pk).update(stock=Decimal("0"))
        token = self.armar_carrito(cantidad="2")
        self.assertTrue(self.confirmar(token).json()["pedido_confirmado"])

    def test_aviso_varios_productos(self):
        texto = texto_aviso_ajuste_precios(
            [
                {"producto": "A", "cantidad": Decimal("1"), "antes": Decimal("10"), "despues": Decimal("12")},
                {"producto": "B", "cantidad": Decimal("2"), "antes": Decimal("5"), "despues": Decimal("4.5")},
            ],
            total=Decimal("21"),
            moneda="MXN",
        )
        self.assertEqual(
            texto,
            "Cambiaron precios del menú: «A» de $10.00 a $12.00; «B» de $5.00 a $4.50. "
            "Tu total ahora es $21.00 MXN.",
        )


class ConfirmacionOtrosGirosSinCambiosTests(TestCase):
    """Fuera de restaurante el stock numérico se sigue validando y descontando."""

    def setUp(self):
        self.empresa = Empresa.objects.create(nombre="Abarrotes Uno", rfc="ABU010101AA1")
        plantilla = Plantilla.objects.create(empresa=self.empresa, nombre="Tienda", tipo="abarrotes", activa=True)
        catalogo = Catalogo.objects.create(
            empresa=self.empresa, plantilla=plantilla, nombre="Tienda", moneda="MXN", activo=True,
        )
        self.producto = Producto.objects.create(
            catalogo=catalogo, sku="ARR-1", nombre="Arroz", precio=Decimal("30.00"),
            stock=Decimal("5"), unidad="kg", activo=True,
        )
        self.pedido = crear_pedido(empresa_id=self.empresa.id, moneda="MXN")

    def test_stock_se_descuenta(self):
        agregar_producto_a_pedido(pedido_id=self.pedido.id, producto_id=self.producto.id, cantidad="2")
        confirmar_pedido(pedido_id=self.pedido.id)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, Decimal("3.0000"))

    def test_stock_insuficiente_se_rechaza(self):
        from django.core.exceptions import ValidationError

        agregar_producto_a_pedido(pedido_id=self.pedido.id, producto_id=self.producto.id, cantidad="6")
        with self.assertRaisesMessage(ValidationError, "Stock insuficiente"):
            confirmar_pedido(pedido_id=self.pedido.id)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, Decimal("5.0000"))
