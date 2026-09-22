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
    ProductoImagen,
    GrupoModificadorProducto,
    OpcionModificadorProducto,
)


class RestauranteApiMenuTests(TestCase):

    def setUp(self):

        self.key_patch = patch(
            "core.views_api._leer_clave_api",
            return_value="r2-menu-test-key",
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
                "Bearer r2-menu-test-key",
        }

        self.empresa = Empresa.objects.create(
            nombre="Restaurante API TEST",
            rfc="RAP010101AA1",
        )

        self.plantilla = Plantilla.objects.create(
            empresa=self.empresa,
            nombre="Restaurante API TEST",
            tipo="restaurante",
            descripcion="",
            identificador_externo="",
            activa=True,
        )

        self.bot = Bot.objects.create(
            empresa=self.empresa,
            plantilla=self.plantilla,
            nombre="Bot Restaurante API TEST",
            activo=True,
        )

        self.catalogo = Catalogo.objects.create(
            empresa=self.empresa,
            plantilla=self.plantilla,
            nombre="Menu API TEST",
            moneda="MXN",
            activo=True,
        )

        self.categoria = (
            CategoriaProducto.objects.create(
                catalogo=self.catalogo,
                nombre="Hamburguesas",
                descripcion="Hamburguesas TEST",
                orden=10,
                activa=True,
            )
        )

        self.producto = Producto.objects.create(
            catalogo=self.catalogo,
            categoria=self.categoria,
            sku="REST-API-001",
            nombre="Hamburguesa Especial",
            descripcion="Carne, queso y vegetales",
            precio=Decimal("100.0000"),
            stock=Decimal("20.0000"),
            unidad="pieza",
            imagen_principal=
                "productos/api/principal.webp",
            activo=True,
        )

        ProductoImagen.objects.create(
            producto=self.producto,
            imagen=
                "productos/api/galeria.webp",
            orden=1,
            activa=True,
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
                orden=1,
                activo=True,
            )
        )

        self.opcion = (
            OpcionModificadorProducto.objects.create(
                grupo=self.grupo,
                nombre="Grande",
                precio_adicional=
                    Decimal("20.0000"),
                orden=1,
                activa=True,
            )
        )

        self.categoria_vacia = (
            CategoriaProducto.objects.create(
                catalogo=self.catalogo,
                nombre="Sin disponibilidad",
                orden=20,
                activa=True,
            )
        )

        # TNL-RESTAURANTE-DISPONIBILIDAD-V1
        # Agotado = producto inactivo; el stock numérico no cuenta.
        Producto.objects.create(
            catalogo=self.catalogo,
            categoria=
                self.categoria_vacia,
            nombre="Producto agotado",
            precio=Decimal("50.0000"),
            stock=Decimal("0.0000"),
            activo=False,
        )

        self.empresa2 = Empresa.objects.create(
            nombre="Otro Restaurante TEST",
            rfc="RAP020202BB2",
        )

        self.plantilla2 = (
            Plantilla.objects.create(
                empresa=self.empresa2,
                nombre="Otro Restaurante",
                tipo="restaurante",
                activa=True,
            )
        )

        self.bot2 = Bot.objects.create(
            empresa=self.empresa2,
            plantilla=self.plantilla2,
            nombre="Bot Otro Restaurante",
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
                nombre="SECRETA OTRO TENANT",
                activa=True,
            )
        )

        self.producto2 = Producto.objects.create(
            catalogo=self.catalogo2,
            categoria=self.categoria2,
            nombre="Producto Otro Tenant",
            precio=Decimal("99.0000"),
            stock=Decimal("10.0000"),
            activo=True,
        )

    def get(
        self,
        name,
        params,
        *,
        auth=True,
    ):

        headers = (
            self.auth
            if auth
            else {}
        )

        return self.client.get(
            reverse(
                f"core:{name}"
            ),
            params,
            **headers,
        )

    def test_01_bearer_es_obligatorio(self):

        response = self.get(
            "api_typebot_restaurante_categorias",
            {
                "bot_id":
                    self.bot.id,
            },
            auth=False,
        )

        self.assertEqual(
            response.status_code,
            401,
        )

        self.assertEqual(
            response["WWW-Authenticate"],
            "Bearer",
        )

    def test_02_categorias_solo_tenant_y_con_disponibilidad(self):

        response = self.get(
            "api_typebot_restaurante_categorias",
            {
                "bot_id":
                    self.bot.id,
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        data = response.json()

        self.assertTrue(
            data["ok"]
        )

        self.assertEqual(
            data["cantidad"],
            1,
        )

        self.assertEqual(
            data["categoria_ids"],
            [
                self.categoria.id
            ],
        )

        self.assertNotIn(
            self.categoria2.id,
            data["categoria_ids"],
        )

        self.assertNotIn(
            self.categoria_vacia.id,
            data["categoria_ids"],
        )

    def test_03_bot_no_restaurante_rechazado(self):

        plantilla = Plantilla.objects.create(
            empresa=self.empresa,
            nombre="Abarrotes TEST",
            tipo="abarrotes",
            activa=True,
        )

        bot = Bot.objects.create(
            empresa=self.empresa,
            plantilla=plantilla,
            nombre="Bot no Restaurante",
            activo=True,
        )

        response = self.get(
            "api_typebot_restaurante_categorias",
            {
                "bot_id":
                    bot.id,
            },
        )

        self.assertEqual(
            response.status_code,
            409,
        )

        self.assertEqual(
            response.json()["codigo"],
            "BOT_NO_RESTAURANTE",
        )

    def test_04_productos_categoria_con_imagen(self):

        response = self.get(
            "api_typebot_restaurante_productos",
            {
                "bot_id":
                    self.bot.id,

                "categoria_id":
                    self.categoria.id,
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        data = response.json()

        self.assertEqual(
            data["cantidad"],
            1,
        )

        item = data["productos"][0]

        self.assertEqual(
            item["id"],
            self.producto.id,
        )

        self.assertEqual(
            item["precio"],
            "100.00",
        )

        self.assertTrue(
            item[
                "requiere_configuracion"
            ]
        )

        self.assertIn(
            "principal.webp",
            item[
                "imagen_principal_url"
            ],
        )

        self.assertNotIn(
            self.producto2.id,
            data["producto_ids"],
        )

    def test_05_detalle_configurador_y_galeria(self):

        response = self.get(
            (
                "api_typebot_restaurante_"
                "producto_detalle"
            ),
            {
                "bot_id":
                    self.bot.id,

                "producto_id":
                    self.producto.id,
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        data = response.json()

        self.assertTrue(
            data[
                "requiere_configuracion"
            ]
        )

        self.assertEqual(
            len(data["grupos"]),
            1,
        )

        grupo = data["grupos"][0]

        self.assertEqual(
            grupo["nombre"],
            "Tamaño",
        )

        self.assertTrue(
            grupo["obligatorio"]
        )

        self.assertEqual(
            grupo["minimo"],
            1,
        )

        self.assertEqual(
            grupo["maximo"],
            1,
        )

        self.assertEqual(
            grupo["opciones"][0]["id"],
            self.opcion.id,
        )

        self.assertEqual(
            grupo["opciones"][0][
                "precio_adicional"
            ],
            "20.00",
        )

        self.assertIn(
            "galeria.webp",
            " ".join(
                data["galeria_urls"]
            ),
        )

    def test_06_categoria_otro_tenant_es_404(self):

        response = self.get(
            "api_typebot_restaurante_productos",
            {
                "bot_id":
                    self.bot.id,

                "categoria_id":
                    self.categoria2.id,
            },
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_07_producto_otro_tenant_es_404(self):

        response = self.get(
            (
                "api_typebot_restaurante_"
                "producto_detalle"
            ),
            {
                "bot_id":
                    self.bot.id,

                "producto_id":
                    self.producto2.id,
            },
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_08_producto_agotado_no_aparece(self):

        response = self.get(
            "api_typebot_restaurante_productos",
            {
                "bot_id":
                    self.bot.id,

                "categoria_id":
                    self.categoria_vacia.id,
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.json()["cantidad"],
            0,
        )

    def test_08b_stock_cero_no_agota_en_restaurante(self):

        # TNL-RESTAURANTE-DISPONIBILIDAD-V1
        Producto.objects.filter(
            nombre="Producto agotado",
        ).update(
            activo=True,
        )

        response = self.get(
            "api_typebot_restaurante_productos",
            {
                "bot_id":
                    self.bot.id,

                "categoria_id":
                    self.categoria_vacia.id,
            },
        )

        self.assertEqual(
            response.json()["cantidad"],
            1,
        )

    def test_09_precio_base_incompatible_rechazado(self):

        self.producto.precio = (
            Decimal("100.1234")
        )

        self.producto.save(
            update_fields=[
                "precio",
            ]
        )

        response = self.get(
            "api_typebot_restaurante_productos",
            {
                "bot_id":
                    self.bot.id,

                "categoria_id":
                    self.categoria.id,
            },
        )

        self.assertEqual(
            response.status_code,
            409,
        )

        self.assertEqual(
            response.json()["codigo"],
            "PRECIO_RESTAURANTE_INVALIDO",
        )

    def test_10_precio_opcion_incompatible_rechazado(self):

        self.opcion.precio_adicional = (
            Decimal("20.1250")
        )

        self.opcion.save(
            update_fields=[
                "precio_adicional",
            ]
        )

        response = self.get(
            (
                "api_typebot_restaurante_"
                "producto_detalle"
            ),
            {
                "bot_id":
                    self.bot.id,

                "producto_id":
                    self.producto.id,
            },
        )

        self.assertEqual(
            response.status_code,
            409,
        )

        self.assertEqual(
            response.json()["codigo"],
            "PRECIO_RESTAURANTE_INVALIDO",
        )
