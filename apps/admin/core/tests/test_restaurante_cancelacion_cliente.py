import json
from decimal import Decimal
from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Bot,
    Catalogo,
    CategoriaProducto,
    ConfiguracionRestaurante,
    Empresa,
    Pedido,
    PedidoEstadoEvento,
    Plantilla,
    Producto,
)
from core.services.pedidos import cancelar_pedido_cliente
from core.views_api import _ia_es_cancelacion_explicita


# TNL-CANCELACION-CLIENTE-V1
class CancelacionClienteTests(TestCase):

    def setUp(self):

        self.key_patch = patch(
            "core.views_api._leer_clave_api",
            return_value="cancel-key",
        )

        self.lifecycle_patch = patch(
            "core.views_api._nl_api_empresa_operativa_error",
            return_value=None,
        )

        self.key_patch.start()
        self.lifecycle_patch.start()

        self.addCleanup(self.key_patch.stop)
        self.addCleanup(self.lifecycle_patch.stop)

        self.auth = {
            "HTTP_AUTHORIZATION": "Bearer cancel-key",
        }

        self.empresa = Empresa.objects.create(
            nombre="Rest Cancel TEST",
            rfc="RCT010101AA1",
        )

        self.bot1 = self._crear_bot("Uno", "CANCEL-1")
        self.bot2 = self._crear_bot("Dos", "CANCEL-2")

        ConfiguracionRestaurante.objects.create(
            empresa=self.empresa,
            costo_envio_fijo=Decimal("35.0000"),
            envio_gratis_desde=Decimal("300.0000"),
            tiempo_estimado_minutos=25,
            habilitada=True,
        )

    def _crear_bot(self, sufijo, sku):

        plantilla = Plantilla.objects.create(
            empresa=self.empresa,
            nombre=f"Rest Cancel {sufijo}",
            tipo="restaurante",
            activa=True,
        )

        bot = Bot.objects.create(
            empresa=self.empresa,
            plantilla=plantilla,
            nombre=f"Bot Cancel {sufijo}",
            activo=True,
        )

        catalogo = Catalogo.objects.create(
            empresa=self.empresa,
            plantilla=plantilla,
            nombre=f"Menu {sufijo}",
            moneda="MXN",
            activo=True,
        )

        categoria = CategoriaProducto.objects.create(
            catalogo=catalogo,
            nombre=f"Categoria {sufijo}",
            activa=True,
        )

        bot.producto_prueba = Producto.objects.create(
            catalogo=catalogo,
            categoria=categoria,
            sku=sku,
            nombre=f"Producto {sufijo}",
            precio=Decimal("100.0000"),
            stock=Decimal("20.0000"),
            activo=True,
        )

        return bot

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    def post(self, name, payload):

        return self.client.post(
            reverse("core:" + name),
            data=json.dumps(payload),
            content_type="application/json",
            **self.auth,
        )

    def crear_pedido(self, estado="carrito", bot=None):
        """
        Crea un carrito real por la API de Typebot y, si se pide,
        lo deja en otro estado directamente en la base de datos.
        """

        bot = bot or self.bot1

        response = self.post(
            "api_typebot_restaurante_pedido_producto_agregar",
            {
                "bot_id": bot.id,
                "producto_id": bot.producto_prueba.id,
                "cantidad": "1.0000",
                "opcion_ids": [],
            },
        )

        self.assertEqual(response.status_code, 200)

        token = response.json()["carrito_token"]

        pedido = Pedido.objects.get(
            identificador_externo="typebot:" + token
        )

        if estado != "carrito":
            Pedido.objects.filter(pk=pedido.pk).update(estado=estado)
            pedido.refresh_from_db()

        return pedido, token

    def cancelar(self, token, bot=None):

        return self.post(
            "api_typebot_restaurante_pedido_cancelar",
            {
                "bot_id": (bot or self.bot1).id,
                "carrito_token": token,
            },
        )

    def ia(self, mensaje, token="", bot=None):

        return self.post(
            "api_typebot_ia_responder",
            {
                "bot_id": (bot or self.bot1).id,
                "mensaje": mensaje,
                "carrito_token": token,
                "remote_jid": "5210000000000@s.whatsapp.net",
                "instance_name": "tnl-test",
            },
        )

    def eventos_cancelacion(self, pedido):

        return PedidoEstadoEvento.objects.filter(
            pedido=pedido,
            estado_nuevo="cancelado",
        )

    # -----------------------------------------------------------------
    # A-F: endpoint de Typebot + servicio
    # -----------------------------------------------------------------

    def test_a_cancelar_carrito(self):

        pedido, token = self.crear_pedido("carrito")

        response = self.cancelar(token)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["pedido_cancelado"])
        self.assertEqual(data["estado"], "cancelado")

        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, "cancelado")

        eventos = self.eventos_cancelacion(pedido)
        self.assertEqual(eventos.count(), 1)
        self.assertEqual(eventos.get().estado_anterior, "carrito")
        self.assertIsNone(eventos.get().usuario_id)

    def test_b_cancelar_confirmado(self):

        pedido, token = self.crear_pedido("confirmado")

        response = self.cancelar(token)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["pedido_cancelado"])

        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, "cancelado")

        eventos = self.eventos_cancelacion(pedido)
        self.assertEqual(eventos.count(), 1)
        self.assertEqual(eventos.get().estado_anterior, "confirmado")

    def test_c_cancelacion_duplicada_es_idempotente(self):

        pedido, token = self.crear_pedido("carrito")

        primera = self.cancelar(token)
        segunda = self.cancelar(token)

        self.assertEqual(primera.status_code, 200)
        self.assertEqual(segunda.status_code, 200)

        data = segunda.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["pedido_cancelado"])
        self.assertIn("ya estaba cancelado", data["mensaje"])

        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, "cancelado")
        self.assertEqual(self.eventos_cancelacion(pedido).count(), 1)

    def test_d_estados_operativos_no_se_cancelan(self):

        for estado in (
            "preparando",
            "listo",
            "en_camino",
            "enviado",
            "entregado",
            "pagado",
        ):
            with self.subTest(estado=estado):

                pedido, token = self.crear_pedido(estado)

                response = self.cancelar(token)

                self.assertEqual(response.status_code, 409)
                data = response.json()
                self.assertFalse(data["ok"])
                self.assertEqual(data["estado"], estado)
                self.assertIn("no se puede cancelar", data["error"])

                pedido.refresh_from_db()
                self.assertEqual(pedido.estado, estado)
                self.assertEqual(
                    PedidoEstadoEvento.objects.filter(pedido=pedido).count(),
                    0,
                )

    def test_e_otro_bot_no_modifica(self):

        pedido, token = self.crear_pedido("confirmado")

        response = self.cancelar(token, bot=self.bot2)

        self.assertEqual(response.status_code, 404)

        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, "confirmado")
        self.assertEqual(self.eventos_cancelacion(pedido).count(), 0)

    def test_e2_token_inexistente_404(self):

        response = self.cancelar(f"r:{self.bot1.id}:" + "a" * 32)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()["ok"])

    def test_f_error_en_evento_revierte_todo(self):

        pedido, _ = self.crear_pedido("confirmado")

        with patch.object(
            PedidoEstadoEvento.objects,
            "create",
            side_effect=DatabaseError("fallo forzado"),
        ):
            with self.assertRaises(DatabaseError):
                cancelar_pedido_cliente(pedido_id=pedido.id)

        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, "confirmado")
        self.assertEqual(
            PedidoEstadoEvento.objects.filter(pedido=pedido).count(),
            0,
        )

    # -----------------------------------------------------------------
    # G-J: IA responder
    # -----------------------------------------------------------------

    @patch(
        "core.views_api._ia_intencion_catalogo_restaurante",
        return_value=True,
    )
    def test_g_ia_cancelacion_explicita_de_carrito(self, catalogo):

        pedido, token = self.crear_pedido("carrito")

        response = self.ia("Quiero cancelar mi pedido", token)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["pedido_cancelado"])
        self.assertIs(data["clear_carrito_token"], True)
        self.assertEqual(data["data"]["clear_carrito_token"], "true")
        self.assertIn(pedido.numero, data["respuesta"])

        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, "cancelado")
        self.assertEqual(self.eventos_cancelacion(pedido).count(), 1)

        # No pasó por el flujo IA normal.
        catalogo.assert_not_called()

    @patch(
        "core.views_api._ia_intencion_catalogo_restaurante",
        return_value=True,
    )
    def test_h_ia_cancela_pedido_confirmado(self, catalogo):

        pedido, token = self.crear_pedido("confirmado")

        response = self.ia("cancelar", token)

        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["clear_carrito_token"], True)

        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, "cancelado")
        self.assertEqual(self.eventos_cancelacion(pedido).count(), 1)
        catalogo.assert_not_called()

    @patch(
        "core.views_api._ia_intencion_catalogo_restaurante",
        return_value=True,
    )
    def test_i_ia_texto_normal_sigue_flujo_existente(self, catalogo):

        pedido, token = self.crear_pedido("carrito")

        response = self.ia("¿Qué me recomiendas?", token)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["ia_accion"], "mostrar_categorias")
        self.assertNotIn("clear_carrito_token", data)
        catalogo.assert_called_once()

        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, "carrito")
        self.assertEqual(
            PedidoEstadoEvento.objects.filter(pedido=pedido).count(),
            0,
        )

    @patch(
        "core.views_api._ia_intencion_catalogo_restaurante",
        return_value=True,
    )
    def test_j_ia_cancelacion_sin_token_no_cancela(self, catalogo):

        pedido, _ = self.crear_pedido("carrito")

        response = self.ia("cancelar mi pedido", token="")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("clear_carrito_token", response.json())
        catalogo.assert_called_once()

        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, "carrito")
        self.assertEqual(Pedido.objects.filter(estado="cancelado").count(), 0)

    @patch(
        "core.views_api._ia_intencion_catalogo_restaurante",
        return_value=True,
    )
    def test_k_ia_cancelacion_en_preparacion_responde_negativa(self, catalogo):

        pedido, token = self.crear_pedido("preparando")

        response = self.ia("cancelar pedido", token)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["pedido_cancelado"])
        self.assertIs(data["clear_carrito_token"], False)
        self.assertEqual(data["data"]["clear_carrito_token"], "false")
        self.assertEqual(data["estado"], "preparando")
        self.assertIn("no se puede cancelar", data["respuesta"])
        catalogo.assert_not_called()

        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, "preparando")
        self.assertEqual(
            PedidoEstadoEvento.objects.filter(pedido=pedido).count(),
            0,
        )

    @patch(
        "core.views_api._ia_intencion_catalogo_restaurante",
        return_value=True,
    )
    def test_l_ia_token_de_otro_bot_no_cancela(self, catalogo):

        pedido, token = self.crear_pedido("carrito", bot=self.bot1)

        response = self.ia("cancelar", token, bot=self.bot2)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("clear_carrito_token", response.json())
        catalogo.assert_called_once()

        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, "carrito")

    def test_m_deteccion_explicita_y_estricta(self):

        for texto in (
            "cancelar",
            "Cancelar",
            "CANCELAR MI PEDIDO",
            "❌ Cancelar pedido",
            "Quiero   cancelár mi pedido",
            "quiero cancelar mi pedido, por favor",
            "cancela el pedido porfa",
            "¡Cancelar!",
        ):
            with self.subTest(texto=texto):
                self.assertTrue(_ia_es_cancelacion_explicita(texto))

        for texto in (
            "",
            "hola",
            "no quiero cancelar",
            "¿cómo cancelo mi pedido?",
            "cancelaron mi pedido?",
            "quiero cancelar la hamburguesa",
            "cancelar y pedir otra cosa",
            "quiero pedir unas alitas",
        ):
            with self.subTest(texto=texto):
                self.assertFalse(_ia_es_cancelacion_explicita(texto))
