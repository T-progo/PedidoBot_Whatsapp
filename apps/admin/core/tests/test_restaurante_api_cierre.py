import json
from decimal import Decimal
from unittest.mock import patch

from django.http import JsonResponse
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Empresa,
    Plantilla,
    Bot,
    Catalogo,
    CategoriaProducto,
    Producto,
    Pedido,
    ConfiguracionRestaurante,
)


class RestauranteApiCierreTests(TestCase):

    def setUp(self):

        self.key_patch = patch(
            "core.views_api._leer_clave_api",
            return_value="r2-close-key",
        )

        self.lifecycle_patch = patch(
            (
                "core.views_api."
                "_nl_api_empresa_operativa_error"
            ),
            return_value=None,
        )

        self.key_patch.start()
        self.lifecycle_patch.start()

        self.addCleanup(
            self.key_patch.stop
        )

        self.addCleanup(
            self.lifecycle_patch.stop
        )

        self.auth = {
            "HTTP_AUTHORIZATION":
                "Bearer r2-close-key",
        }

        self.empresa = Empresa.objects.create(
            nombre="Rest Scope TEST",
            rfc="RSC010101AA1",
        )

        self.plantilla1 = Plantilla.objects.create(
            empresa=self.empresa,
            nombre="Rest Scope Uno",
            tipo="restaurante",
            activa=True,
        )

        self.plantilla2 = Plantilla.objects.create(
            empresa=self.empresa,
            nombre="Rest Scope Dos",
            tipo="restaurante",
            activa=True,
        )

        self.bot1 = Bot.objects.create(
            empresa=self.empresa,
            plantilla=self.plantilla1,
            nombre="Bot Scope Uno",
            activo=True,
        )

        self.bot2 = Bot.objects.create(
            empresa=self.empresa,
            plantilla=self.plantilla2,
            nombre="Bot Scope Dos",
            activo=True,
        )

        self.catalogo1 = Catalogo.objects.create(
            empresa=self.empresa,
            plantilla=self.plantilla1,
            nombre="Menu Uno",
            moneda="MXN",
            activo=True,
        )

        self.catalogo2 = Catalogo.objects.create(
            empresa=self.empresa,
            plantilla=self.plantilla2,
            nombre="Menu Dos",
            moneda="MXN",
            activo=True,
        )

        self.categoria1 = (
            CategoriaProducto.objects.create(
                catalogo=self.catalogo1,
                nombre="Categoria Uno",
                activa=True,
            )
        )

        self.categoria2 = (
            CategoriaProducto.objects.create(
                catalogo=self.catalogo2,
                nombre="Categoria Dos",
                activa=True,
            )
        )

        self.producto1 = Producto.objects.create(
            catalogo=self.catalogo1,
            categoria=self.categoria1,
            sku="SCOPE-1",
            nombre="Producto Uno",
            precio=Decimal("100.0000"),
            stock=Decimal("20.0000"),
            activo=True,
        )

        self.producto2 = Producto.objects.create(
            catalogo=self.catalogo2,
            categoria=self.categoria2,
            sku="SCOPE-2",
            nombre="Producto Dos",
            precio=Decimal("100.0000"),
            stock=Decimal("20.0000"),
            activo=True,
        )

        ConfiguracionRestaurante.objects.create(
            empresa=self.empresa,
            costo_envio_fijo=
                Decimal("35.0000"),
            envio_gratis_desde=
                Decimal("300.0000"),
            tiempo_estimado_minutos=25,
            habilitada=True,
        )

    def post(self, name, payload):

        return self.client.post(
            reverse(
                "core:" + name
            ),
            data=json.dumps(
                payload
            ),
            content_type="application/json",
            **self.auth,
        )

    def crear_carrito_bot1(self):

        response = self.post(
            (
                "api_typebot_restaurante_"
                "pedido_producto_agregar"
            ),
            {
                "bot_id":
                    self.bot1.id,

                "producto_id":
                    self.producto1.id,

                "cantidad":
                    "1.0000",

                "opcion_ids":
                    [],
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        return response.json()

    def guardar_cliente(
        self,
        token,
    ):

        response = self.post(
            (
                "api_typebot_restaurante_"
                "pedido_datos"
            ),
            {
                "bot_id":
                    self.bot1.id,

                "carrito_token":
                    token,

                "cliente_nombre":
                    "Cliente Scope",

                "cliente_telefono":
                    "3312345678",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

    def test_01_token_incluye_scope_bot(self):

        data = self.crear_carrito_bot1()

        token = data[
            "carrito_token"
        ]

        prefix = (
            f"r:{self.bot1.id}:"
        )

        self.assertTrue(
            token.startswith(
                prefix
            )
        )

        random_part = token[
            len(prefix):
        ]

        self.assertEqual(
            len(random_part),
            32,
        )

        int(
            random_part,
            16,
        )

        pedido = Pedido.objects.get(
            id=data["pedido_id"]
        )

        self.assertEqual(
            pedido.identificador_externo,
            "typebot:" + token,
        )

    def test_02_mismo_empresa_otro_bot_no_lee_token(self):

        token = self.crear_carrito_bot1()[
            "carrito_token"
        ]

        response = self.client.get(
            reverse(
                (
                    "core:"
                    "api_typebot_restaurante_"
                    "pedido_resumen"
                )
            ),
            {
                "bot_id":
                    self.bot2.id,

                "carrito_token":
                    token,
            },
            **self.auth,
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_03_mismo_empresa_otro_bot_no_agrega(self):

        token = self.crear_carrito_bot1()[
            "carrito_token"
        ]

        response = self.post(
            (
                "api_typebot_restaurante_"
                "pedido_producto_agregar"
            ),
            {
                "bot_id":
                    self.bot2.id,

                "producto_id":
                    self.producto2.id,

                "cantidad":
                    "1.0000",

                "opcion_ids":
                    [],

                "carrito_token":
                    token,
            },
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_04_token_no_scoped_rechazado(self):

        token = (
            "0123456789abcdef"
            "0123456789abcdef"
        )

        Pedido.objects.create(
            empresa=self.empresa,
            numero="PED-999990",
            estado="carrito",
            moneda="MXN",
            identificador_externo=
                "typebot:" + token,
        )

        response = self.client.get(
            reverse(
                (
                    "core:"
                    "api_typebot_restaurante_"
                    "pedido_resumen"
                )
            ),
            {
                "bot_id":
                    self.bot1.id,

                "carrito_token":
                    token,
            },
            **self.auth,
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_05_checkout_otro_bot_bloqueado_antes_delegate(self):

        token = self.crear_carrito_bot1()[
            "carrito_token"
        ]

        with patch(
            (
                "core.views_api."
                "carrito_mercadopago_checkout"
            )
        ) as checkout:

            response = self.post(
                (
                    "api_typebot_restaurante_"
                    "pedido_mercadopago_checkout"
                ),
                {
                    "bot_id":
                        self.bot2.id,

                    "carrito_token":
                        token,
                },
            )

        self.assertEqual(
            response.status_code,
            404,
        )

        checkout.assert_not_called()

    def test_06_checkout_bot_correcto_delega(self):

        token = self.crear_carrito_bot1()[
            "carrito_token"
        ]

        fake = JsonResponse(
            {
                "ok": True,
                "delegado": True,
            }
        )

        with patch(
            (
                "core.views_api."
                "carrito_mercadopago_checkout"
            ),
            return_value=fake,
        ) as checkout:

            response = self.post(
                (
                    "api_typebot_restaurante_"
                    "pedido_mercadopago_checkout"
                ),
                {
                    "bot_id":
                        self.bot1.id,

                    "carrito_token":
                        token,
                },
            )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTrue(
            response.json()[
                "delegado"
            ]
        )

        checkout.assert_called_once()

    def test_07_cancelar_bot_correcto(self):

        token = self.crear_carrito_bot1()[
            "carrito_token"
        ]

        response = self.post(
            (
                "api_typebot_restaurante_"
                "pedido_cancelar"
            ),
            {
                "bot_id":
                    self.bot1.id,

                "carrito_token":
                    token,
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        pedido = Pedido.objects.get(
            identificador_externo=
                "typebot:" + token
        )

        self.assertEqual(
            pedido.estado,
            "cancelado",
        )

    def test_08_cancelar_otro_bot_no_modifica(self):

        token = self.crear_carrito_bot1()[
            "carrito_token"
        ]

        response = self.post(
            (
                "api_typebot_restaurante_"
                "pedido_cancelar"
            ),
            {
                "bot_id":
                    self.bot2.id,

                "carrito_token":
                    token,
            },
        )

        self.assertEqual(
            response.status_code,
            404,
        )

        pedido = Pedido.objects.get(
            identificador_externo=
                "typebot:" + token
        )

        self.assertEqual(
            pedido.estado,
            "carrito",
        )

    def test_09_consulta_numero_telefono_bot_correcto(self):

        data = self.crear_carrito_bot1()

        token = data[
            "carrito_token"
        ]

        self.guardar_cliente(
            token
        )

        response = self.client.get(
            reverse(
                (
                    "core:"
                    "api_typebot_restaurante_"
                    "pedido_consultar"
                )
            ),
            {
                "bot_id":
                    self.bot1.id,

                "numero":
                    data[
                        "pedido_numero"
                    ],

                "telefono":
                    "3312345678",
            },
            **self.auth,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTrue(
            response.json()[
                "encontrado"
            ]
        )

    def test_10_consulta_otro_bot_no_revela_pedido(self):

        data = self.crear_carrito_bot1()

        self.guardar_cliente(
            data[
                "carrito_token"
            ]
        )

        response = self.client.get(
            reverse(
                (
                    "core:"
                    "api_typebot_restaurante_"
                    "pedido_consultar"
                )
            ),
            {
                "bot_id":
                    self.bot2.id,

                "numero":
                    data[
                        "pedido_numero"
                    ],

                "telefono":
                    "3312345678",
            },
            **self.auth,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        payload = (
            response.json()
        )

        self.assertFalse(
            payload[
                "encontrado"
            ]
        )

        self.assertNotIn(
            "pedido_numero",
            payload,
        )
