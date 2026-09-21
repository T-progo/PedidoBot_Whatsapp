import json
from decimal import Decimal
from unittest.mock import patch

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
    PedidoDetalle,
    ConfiguracionRestaurante,
    GrupoModificadorProducto,
    OpcionModificadorProducto,
)


class RestauranteApiPedidoTests(TestCase):

    def setUp(self):

        self.key_patch = patch(
            "core.views_api._leer_clave_api",
            return_value="r2-pedido-test-key",
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
                "Bearer r2-pedido-test-key",
        }

        self.empresa = Empresa.objects.create(
            nombre="Rest API Pedido TEST",
            rfc="RPC010101AA1",
        )

        self.plantilla = Plantilla.objects.create(
            empresa=self.empresa,
            nombre="Rest Pedido TEST",
            tipo="restaurante",
            activa=True,
        )

        self.bot = Bot.objects.create(
            empresa=self.empresa,
            plantilla=self.plantilla,
            nombre="Bot Pedido TEST",
            activo=True,
        )

        self.catalogo = Catalogo.objects.create(
            empresa=self.empresa,
            plantilla=self.plantilla,
            nombre="Menu Pedido TEST",
            moneda="MXN",
            activo=True,
        )

        self.categoria = (
            CategoriaProducto.objects.create(
                catalogo=self.catalogo,
                nombre="Hamburguesas",
                activa=True,
            )
        )

        self.producto = Producto.objects.create(
            catalogo=self.catalogo,
            categoria=self.categoria,
            sku="R2-PED-001",
            nombre="Hamburguesa",
            precio=Decimal("100.0000"),
            stock=Decimal("20.0000"),
            unidad="pieza",
            activo=True,
        )

        self.config = (
            ConfiguracionRestaurante.objects.create(
                empresa=self.empresa,
                costo_envio_fijo=
                    Decimal("35.0000"),
                envio_gratis_desde=
                    Decimal("300.0000"),
                tiempo_estimado_minutos=25,
                habilitada=True,
            )
        )

        self.grupo = (
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
                activo=True,
            )
        )

        self.opcion = (
            OpcionModificadorProducto.objects.create(
                grupo=self.grupo,
                nombre="Grande",
                precio_adicional=
                    Decimal("20.0000"),
                activa=True,
            )
        )

        self.empresa2 = Empresa.objects.create(
            nombre="Otro Rest Pedido",
            rfc="RPC020202BB2",
        )

        self.plantilla2 = Plantilla.objects.create(
            empresa=self.empresa2,
            nombre="Otro Rest Pedido",
            tipo="restaurante",
            activa=True,
        )

        self.bot2 = Bot.objects.create(
            empresa=self.empresa2,
            plantilla=self.plantilla2,
            nombre="Bot Otro Pedido",
            activo=True,
        )

        self.catalogo2 = Catalogo.objects.create(
            empresa=self.empresa2,
            plantilla=self.plantilla2,
            nombre="Menu Otro",
            moneda="MXN",
            activo=True,
        )

        self.categoria2 = (
            CategoriaProducto.objects.create(
                catalogo=self.catalogo2,
                nombre="Otra Categoria",
                activa=True,
            )
        )

        self.producto2 = Producto.objects.create(
            catalogo=self.catalogo2,
            categoria=self.categoria2,
            nombre="Producto Secreto",
            precio=Decimal("50.0000"),
            stock=Decimal("10.0000"),
            activo=True,
        )

    def post(self, name, payload):

        return self.client.post(
            reverse(
                f"core:{name}"
            ),
            data=json.dumps(
                payload
            ),
            content_type="application/json",
            **self.auth,
        )

    def agregar(
        self,
        *,
        carrito_token="",
        bot_id=None,
        producto_id=None,
        opcion_ids=None,
        cantidad="1.0000",
        suprimir_cross_sell=None,
    ):

        payload = {
            "bot_id":
                bot_id or self.bot.id,

            "producto_id":
                (
                    producto_id
                    or self.producto.id
                ),

            "cantidad":
                cantidad,

            "opcion_ids":
                (
                    [self.opcion.id]
                    if opcion_ids is None
                    else opcion_ids
                ),
        }

        if carrito_token:

            payload[
                "carrito_token"
            ] = carrito_token


        if (
            suprimir_cross_sell
            is not None
        ):

            payload[
                "suprimir_cross_sell"
            ] = suprimir_cross_sell


        return self.post(
            (
                "api_typebot_restaurante_"
                "pedido_producto_agregar"
            ),
            payload,
        )

    # ========================================================
    # TNL-RESTAURANTE-CROSSSELL-TESTS-V1
    # ========================================================

    def test_cross_sell_activo_en_respuesta_agregar(
        self,
    ):

        from core.models import (
            Producto,
            ReglaVentaCruzadaIA,
        )


        recomendado = (
            Producto.objects.create(
                catalogo=
                    self.producto.catalogo,

                categoria=
                    self.producto.categoria,

                sku=
                    "CROSS-SELL-ACTIVO-001",

                nombre=
                    "Hamburguesa doble TEST",

                descripcion=
                    "",

                precio=
                    "180.0000",

                stock=
                    "9.0000",

                unidad=
                    self.producto.unidad,

                identificador_externo=
                    "cross-sell-activo-001",

                activo=True,
            )
        )


        regla = (
            ReglaVentaCruzadaIA.objects.create(
                empresa=
                    self.bot.empresa,

                producto_origen=
                    self.producto,

                producto_recomendado=
                    recomendado,

                texto_promocional=(
                    "Ya adquiriste "
                    "{{producto_origen}}. "
                    "¿Deseas agregar "
                    "{{producto_recomendado}} "
                    "por "
                    "{{precio_recomendado}}?"
                ),

                activa=True,
                prioridad=10,
            )
        )


        response = self.agregar()


        self.assertEqual(
            response.status_code,
            200,
        )


        data = response.json()


        self.assertTrue(
            data[
                "cross_sell_disponible"
            ]
        )


        self.assertEqual(
            data[
                "cross_sell_regla_id"
            ],
            regla.id,
        )


        self.assertEqual(
            data[
                "cross_sell_producto_id"
            ],
            recomendado.id,
        )


        self.assertEqual(
            data[
                "cross_sell_producto_nombre"
            ],
            "Hamburguesa doble TEST",
        )


        self.assertEqual(
            data[
                "cross_sell_precio"
            ],
            "180.00",
        )


        self.assertEqual(
            data[
                "cross_sell_moneda"
            ],
            self.producto.catalogo.moneda,
        )


        self.assertEqual(
            data[
                "cross_sell_precio_texto"
            ],
            (
                "$180.00 "
                +
                self.producto.catalogo.moneda
            ),
        )


        self.assertIn(
            self.producto.nombre,
            data[
                "cross_sell_mensaje"
            ],
        )


        self.assertIn(
            recomendado.nombre,
            data[
                "cross_sell_mensaje"
            ],
        )


        self.assertIn(
            "$180.00",
            data[
                "cross_sell_mensaje"
            ],
        )


        recomendado.refresh_from_db()


        self.assertEqual(
            str(
                recomendado.stock
            ),
            "9.0000",
        )



    def test_cross_sell_inactivo_no_se_ofrece(
        self,
    ):

        from core.models import (
            Producto,
            ReglaVentaCruzadaIA,
        )


        recomendado = (
            Producto.objects.create(
                catalogo=
                    self.producto.catalogo,

                categoria=
                    self.producto.categoria,

                sku=
                    "CROSS-SELL-INACTIVO-001",

                nombre=
                    "Cross sell inactivo TEST",

                descripcion=
                    "",

                precio=
                    "75.0000",

                stock=
                    "5.0000",

                unidad=
                    self.producto.unidad,

                identificador_externo=
                    "cross-sell-inactivo-001",

                activo=True,
            )
        )


        ReglaVentaCruzadaIA.objects.create(
            empresa=
                self.bot.empresa,

            producto_origen=
                self.producto,

            producto_recomendado=
                recomendado,

            texto_promocional=
                "Esta oferta no debe aparecer.",

            activa=False,
            prioridad=10,
        )


        response = self.agregar()


        self.assertEqual(
            response.status_code,
            200,
        )


        data = response.json()


        self.assertFalse(
            data[
                "cross_sell_disponible"
            ]
        )


        self.assertIsNone(
            data[
                "cross_sell_regla_id"
            ]
        )


        self.assertIsNone(
            data[
                "cross_sell_producto_id"
            ]
        )


        self.assertEqual(
            data[
                "cross_sell_producto_nombre"
            ],
            "",
        )


        self.assertEqual(
            data[
                "cross_sell_precio"
            ],
            "",
        )


        self.assertEqual(
            data[
                "cross_sell_mensaje"
            ],
            "",
        )



    def test_cross_sell_sin_stock_no_se_ofrece(
        self,
    ):

        from core.models import (
            Producto,
            ReglaVentaCruzadaIA,
        )


        recomendado = (
            Producto.objects.create(
                catalogo=
                    self.producto.catalogo,

                categoria=
                    self.producto.categoria,

                sku=
                    "CROSS-SELL-STOCK-000",

                nombre=
                    "Cross sell sin stock TEST",

                descripcion=
                    "",

                precio=
                    "99.0000",

                stock=
                    "0.0000",

                unidad=
                    self.producto.unidad,

                identificador_externo=
                    "cross-sell-stock-000",

                activo=True,
            )
        )


        ReglaVentaCruzadaIA.objects.create(
            empresa=
                self.bot.empresa,

            producto_origen=
                self.producto,

            producto_recomendado=
                recomendado,

            texto_promocional=(
                "No debe ofrecerse "
                "porque no hay stock."
            ),

            activa=True,
            prioridad=10,
        )


        response = self.agregar()


        self.assertEqual(
            response.status_code,
            200,
        )


        data = response.json()


        self.assertFalse(
            data[
                "cross_sell_disponible"
            ]
        )


        self.assertIsNone(
            data[
                "cross_sell_producto_id"
            ]
        )


    def test_cross_sell_suprimido_no_se_ofrece(
        self,
    ):

        from core.models import (
            Producto,
            ReglaVentaCruzadaIA,
        )


        recomendado = (
            Producto.objects.create(
                catalogo=
                    self.producto.catalogo,

                categoria=
                    self.producto.categoria,

                sku=
                    "CROSS-SELL-SUPPRESS-001",

                nombre=
                    "Cross sell suprimido TEST",

                descripcion=
                    "",

                precio=
                    "125.0000",

                stock=
                    "8.0000",

                unidad=
                    self.producto.unidad,

                identificador_externo=
                    "cross-sell-suppress-001",

                activo=True,
            )
        )


        ReglaVentaCruzadaIA.objects.create(
            empresa=
                self.bot.empresa,

            producto_origen=
                self.producto,

            producto_recomendado=
                recomendado,

            texto_promocional=(
                "Esta promoción existe, "
                "pero debe ser suprimida."
            ),

            activa=True,
            prioridad=1,
        )


        response = self.agregar(
            suprimir_cross_sell=True,
        )


        self.assertEqual(
            response.status_code,
            200,
        )


        data = response.json()


        self.assertTrue(
            data["ok"]
        )


        self.assertFalse(
            data[
                "cross_sell_disponible"
            ]
        )


        self.assertIsNone(
            data[
                "cross_sell_producto_id"
            ]
        )


        self.assertEqual(
            data[
                "cross_sell_mensaje"
            ],
            "",
        )


        # El producto original sí debe agregarse.
        self.assertEqual(
            data[
                "cantidad_lineas"
            ],
            1,
        )


        # El recomendado NO fue agregado.
        recomendado.refresh_from_db()

        self.assertEqual(
            str(
                recomendado.stock
            ),
            "8.0000",
        )



    def preparar_comedor(self):

        response = self.agregar()
        self.assertEqual(
            response.status_code,
            200,
        )

        token = (
            response.json()[
                "carrito_token"
            ]
        )

        response = self.post(
            (
                "api_typebot_restaurante_"
                "pedido_datos"
            ),
            {
                "bot_id":
                    self.bot.id,

                "carrito_token":
                    token,

                "cliente_nombre":
                    "Cliente TEST",

                "cliente_telefono":
                    "3312345678",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        response = self.post(
            (
                "api_typebot_restaurante_"
                "pedido_logistica"
            ),
            {
                "bot_id":
                    self.bot.id,

                "carrito_token":
                    token,

                "tipo_orden":
                    "comedor",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        return token

    def test_01_bearer_obligatorio(self):

        response = self.client.post(
            reverse(
                (
                    "core:"
                    "api_typebot_restaurante_"
                    "pedido_producto_agregar"
                )
            ),
            data=json.dumps(
                {
                    "bot_id":
                        self.bot.id,

                    "producto_id":
                        self.producto.id,

                    "cantidad":
                        "1.0000",

                    "opcion_ids":
                        [self.opcion.id],
                }
            ),
            content_type=
                "application/json",
        )

        self.assertEqual(
            response.status_code,
            401,
        )

    def test_02_agregar_crea_carrito_por_servicio(self):

        response = self.agregar()

        self.assertEqual(
            response.status_code,
            200,
        )

        data = response.json()

        self.assertTrue(
            data["carrito_creado"]
        )

        self.assertTrue(
            data["pedido_numero"].startswith(
                "PED-"
            )
        )

        pedido = Pedido.objects.get(
            id=data["pedido_id"]
        )

        self.assertEqual(
            pedido.identificador_externo,
            (
                "typebot:"
                +
                data["carrito_token"]
            ),
        )

        self.assertEqual(
            data["precio_modificadores"]
            if "precio_modificadores" in data
            else
            data["lineas"][0][
                "precio_modificadores"
            ],
            "20.00",
        )

        self.assertEqual(
            data["total"],
            "120.00",
        )

    def test_03_mismo_producto_puede_tener_varias_lineas(self):

        first = self.agregar()
        token = first.json()[
            "carrito_token"
        ]

        second = self.agregar(
            carrito_token=token,
        )

        self.assertEqual(
            second.status_code,
            200,
        )

        self.assertFalse(
            second.json()[
                "carrito_creado"
            ]
        )

        pedido = Pedido.objects.get(
            identificador_externo=
                "typebot:" + token,
        )

        self.assertEqual(
            pedido.detalles.count(),
            2,
        )

        self.assertEqual(
            pedido.total,
            Decimal("240.0000"),
        )

    def test_04_error_configuracion_hace_rollback_de_carrito_nuevo(self):

        before = Pedido.objects.count()

        response = self.agregar(
            opcion_ids=[],
        )

        self.assertEqual(
            response.status_code,
            409,
        )

        self.assertEqual(
            Pedido.objects.count(),
            before,
        )

        self.assertEqual(
            PedidoDetalle.objects.count(),
            0,
        )

    def test_05_producto_otro_tenant_rechazado(self):

        response = self.agregar(
            producto_id=
                self.producto2.id,
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_06_datos_cliente_sin_direccion(self):

        response = self.agregar()
        token = response.json()[
            "carrito_token"
        ]

        identificador = (
            "typebot:" + token
        )

        response = self.post(
            (
                "api_typebot_restaurante_"
                "pedido_datos"
            ),
            {
                "bot_id":
                    self.bot.id,

                "carrito_token":
                    token,

                "cliente_nombre":
                    "Juan TEST",

                "cliente_telefono":
                    "3311111111",

                "cliente_email":
                    "juan@example.com",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        pedido = Pedido.objects.get(
            identificador_externo=
                identificador
        )

        self.assertEqual(
            pedido.cliente_nombre,
            "Juan TEST",
        )

        self.assertEqual(
            pedido.direccion_entrega,
            "",
        )

        self.assertEqual(
            pedido.identificador_externo,
            identificador,
        )

    def test_07_comedor_no_requiere_direccion(self):

        response = self.agregar()
        token = response.json()[
            "carrito_token"
        ]

        response = self.post(
            (
                "api_typebot_restaurante_"
                "pedido_logistica"
            ),
            {
                "bot_id":
                    self.bot.id,

                "carrito_token":
                    token,

                "tipo_orden":
                    "comedor",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        data = response.json()

        self.assertEqual(
            data["tipo_orden"],
            "comedor",
        )

        self.assertEqual(
            data["costo_envio"],
            "0.00",
        )

    def test_08_domicilio_sin_direccion_hace_rollback(self):

        response = self.agregar()
        token = response.json()[
            "carrito_token"
        ]

        response = self.post(
            (
                "api_typebot_restaurante_"
                "pedido_logistica"
            ),
            {
                "bot_id":
                    self.bot.id,

                "carrito_token":
                    token,

                "tipo_orden":
                    "domicilio",
            },
        )

        self.assertEqual(
            response.status_code,
            409,
        )

        pedido = Pedido.objects.get(
            identificador_externo=
                "typebot:" + token
        )

        self.assertEqual(
            pedido.tipo_orden,
            "",
        )

    def test_09_domicilio_aplica_envio(self):

        response = self.agregar()
        token = response.json()[
            "carrito_token"
        ]

        response = self.post(
            (
                "api_typebot_restaurante_"
                "pedido_logistica"
            ),
            {
                "bot_id":
                    self.bot.id,

                "carrito_token":
                    token,

                "tipo_orden":
                    "domicilio",

                "direccion_entrega":
                    "Calle TEST 123",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        data = response.json()

        self.assertEqual(
            data["costo_envio"],
            "35.00",
        )

        self.assertEqual(
            data["total"],
            "155.00",
        )

    def test_10_resumen_incluye_snapshots(self):

        response = self.agregar()
        token = response.json()[
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
                    self.bot.id,

                "carrito_token":
                    token,
            },
            **self.auth,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        data = response.json()

        self.assertEqual(
            data["cantidad_lineas"],
            1,
        )

        linea = data["lineas"][0]

        self.assertEqual(
            linea["precio_base"],
            "100.00",
        )

        self.assertEqual(
            linea["precio_modificadores"],
            "20.00",
        )

        self.assertEqual(
            len(
                linea[
                    "modificadores"
                ]
            ),
            1,
        )

        # TNL-RESTAURANTE-RESUMEN-TEXTO-V1
        self.assertIn(
            "resumen_texto",
            data,
        )

        resumen_texto = (
            data[
                "resumen_texto"
            ]
        )

        self.assertIn(
            (
                "🧾 Pedido "
                f"{data['pedido_numero']}"
            ),
            resumen_texto,
        )

        self.assertIn(
            linea[
                "nombre"
            ],
            resumen_texto,
        )

        self.assertIn(
            (
                "$"
                f"{linea['importe']}"
            ),
            resumen_texto,
        )

        self.assertIn(
            (
                "TOTAL: $"
                f"{data['total']} "
                f"{data['moneda']}"
            ),
            resumen_texto,
        )

        self.assertNotIn(
            "vdwb12vu21fqvvqnelp0wdw1o",
            resumen_texto,
        )

    def test_11_confirmar_comedor_sin_direccion(self):

        token = self.preparar_comedor()

        stock_before = (
            self.producto.stock
        )

        response = self.post(
            (
                "api_typebot_restaurante_"
                "pedido_confirmar"
            ),
            {
                "bot_id":
                    self.bot.id,

                "carrito_token":
                    token,
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        data = response.json()

        self.assertTrue(
            data["pedido_confirmado"]
        )

        self.assertEqual(
            data["estado"],
            "confirmado",
        )

        self.producto.refresh_from_db()

        self.assertEqual(
            self.producto.stock,
            stock_before
            -
            Decimal("1.0000"),
        )

    def test_12_confirmar_sin_logistica_rechazado(self):

        response = self.agregar()
        token = response.json()[
            "carrito_token"
        ]

        self.post(
            (
                "api_typebot_restaurante_"
                "pedido_datos"
            ),
            {
                "bot_id":
                    self.bot.id,

                "carrito_token":
                    token,

                "cliente_nombre":
                    "Cliente TEST",

                "cliente_telefono":
                    "3312345678",
            },
        )

        response = self.post(
            (
                "api_typebot_restaurante_"
                "pedido_confirmar"
            ),
            {
                "bot_id":
                    self.bot.id,

                "carrito_token":
                    token,
            },
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        pedido = Pedido.objects.get(
            identificador_externo=
                "typebot:" + token
        )

        self.assertEqual(
            pedido.estado,
            "carrito",
        )

    def test_13_token_no_cruza_empresa(self):

        response = self.agregar()
        token = response.json()[
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

    def test_14_pedido_confirmado_no_acepta_producto(self):

        token = self.preparar_comedor()

        response = self.post(
            (
                "api_typebot_restaurante_"
                "pedido_confirmar"
            ),
            {
                "bot_id":
                    self.bot.id,

                "carrito_token":
                    token,
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        response = self.agregar(
            carrito_token=token,
        )

        self.assertEqual(
            response.status_code,
            409,
        )
