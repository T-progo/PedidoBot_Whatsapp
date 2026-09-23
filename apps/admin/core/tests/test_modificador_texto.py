"""
Selección de modificadores escrita a mano (TNL-MODIFICADOR-TEXTO-V1).

El texto del cliente se resuelve contra las opciones del grupo
ACTUAL: nunca contra otro grupo, nunca contra opciones
inactivas y nunca aceptando precios del cliente.
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
import json

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Bot,
    Catalogo,
    CategoriaProducto,
    ConfiguracionRestaurante,
    Empresa,
    GrupoModificadorProducto,
    Licencia,
    OpcionModificadorProducto,
    Plantilla,
    Producto,
)
from core.services.seleccion_modificadores import resolver_texto_opciones


class ResolverTextoOpcionesTests(TestCase):
    """Reglas puras, sin base de datos."""

    def setUp(self):

        self.ids = [11, 12, 13]

        self.nombres = [
            "BBQ",
            "Búfalo hot",
            "Mango habanero",
        ]

        self.etiquetas = [
            "1. BBQ (+5.00)",
            "2. Búfalo hot (+5.00)",
            "3. Mango habanero (+5.00)",
        ]

    def resolver(self, texto, *, maximo=3, seleccionadas=None):
        return resolver_texto_opciones(
            texto=texto,
            opcion_ids=self.ids,
            opcion_nombres=self.nombres,
            opcion_etiquetas=self.etiquetas,
            maximo=maximo,
            seleccionadas=seleccionadas or [],
        )

    def test_01_numero_simple(self):

        resultado = self.resolver("1")

        self.assertTrue(resultado["resuelto"])

        self.assertEqual(
            resultado["opcion_ids"],
            [11],
        )

    def test_02_nombre_exacto(self):

        self.assertEqual(
            self.resolver("BBQ")["opcion_ids"],
            [11],
        )

    def test_03_nombre_sin_mayusculas_ni_acentos(self):

        for texto in (
            "bbq",
            "BUFALO HOT",
            "bufalo hot",
            "Búfalo Hot",
        ):
            resultado = self.resolver(texto)

            self.assertTrue(
                resultado["resuelto"],
                texto,
            )

    def test_04_varios_numeros_para_extras(self):

        for texto in (
            "1 y 3",
            "1, 3",
            "1 3",
            "1,3",
        ):
            resultado = self.resolver(texto)

            self.assertEqual(
                resultado["opcion_ids"],
                [11, 13],
                texto,
            )

    def test_05_repetido_en_el_mismo_mensaje(self):

        resultado = self.resolver("1 y 1")

        self.assertFalse(resultado["resuelto"])

        self.assertEqual(
            resultado["motivo"],
            "repetida_en_mensaje",
        )

    def test_06_ya_elegida_antes(self):

        resultado = self.resolver(
            "1",
            seleccionadas=[11],
        )

        self.assertFalse(resultado["resuelto"])

        self.assertEqual(
            resultado["motivo"],
            "ya_elegida",
        )

        self.assertEqual(
            resultado["acumuladas"],
            [11],
        )

    def test_07_numero_fuera_de_rango(self):

        resultado = self.resolver("9")

        self.assertFalse(resultado["resuelto"])

        self.assertEqual(
            resultado["motivo"],
            "numero_invalido",
        )

        self.assertIn(
            "entre 1 y 3",
            resultado["mensaje"],
        )

    def test_08_nombre_inexistente(self):

        resultado = self.resolver("pizza hawaiana")

        self.assertFalse(resultado["resuelto"])

        self.assertEqual(
            resultado["motivo"],
            "nombre_invalido",
        )

    def test_09_grupo_de_una_sola_opcion_rechaza_varias(self):

        resultado = self.resolver(
            "1 y 3",
            maximo=1,
        )

        self.assertFalse(resultado["resuelto"])

        self.assertEqual(
            resultado["motivo"],
            "solo_una",
        )

    def test_10_respeta_el_maximo_del_grupo(self):

        resultado = self.resolver(
            "2 y 3",
            maximo=2,
            seleccionadas=[11],
        )

        self.assertFalse(resultado["resuelto"])

        self.assertEqual(
            resultado["motivo"],
            "maximo",
        )

    def test_11_acumula_sobre_lo_ya_elegido(self):

        resultado = self.resolver(
            "3",
            seleccionadas=[11],
        )

        self.assertEqual(
            resultado["acumuladas"],
            [11, 13],
        )

    def test_12_texto_vacio(self):

        self.assertEqual(
            self.resolver("   ")["motivo"],
            "vacio",
        )

    def test_13_ambiguedad_pide_numero(self):

        resultado = resolver_texto_opciones(
            texto="bbq",
            opcion_ids=[1, 2],
            opcion_nombres=[
                "BBQ dulce",
                "BBQ picante",
            ],
            maximo=2,
            seleccionadas=[],
        )

        self.assertFalse(resultado["resuelto"])

        self.assertEqual(
            resultado["motivo"],
            "ambiguo",
        )


class ResolverEndpointTests(TestCase):
    """El endpoint sólo ve el grupo actual del producto."""

    CLAVE = "modificador-texto-test-key"

    def setUp(self):

        # Mismo patrón que el resto de pruebas de la API.
        clave_patch = patch(
            "core.views_api._leer_clave_api",
            return_value=self.CLAVE,
        )

        lifecycle_patch = patch(
            (
                "core.views_api."
                "_nl_api_empresa_operativa_error"
            ),
            return_value=None,
        )

        clave_patch.start()
        lifecycle_patch.start()

        self.addCleanup(clave_patch.stop)
        self.addCleanup(lifecycle_patch.stop)

        hoy = timezone.localdate()

        self.empresa = Empresa.objects.create(
            nombre="Restaurante TEXTO",
            rfc="RTX010101AA1",
        )

        Licencia.objects.create(
            empresa=self.empresa,
            nombre="Licencia TEXTO",
            estado="activa",
            fecha_inicio=hoy - timedelta(days=1),
            fecha_fin=hoy + timedelta(days=30),
        )

        ConfiguracionRestaurante.objects.create(
            empresa=self.empresa,
            costo_envio_fijo=Decimal("0.0000"),
            envio_gratis_desde=Decimal("0.0000"),
            tiempo_estimado_minutos=20,
            habilitada=True,
        )

        self.plantilla = Plantilla.objects.create(
            empresa=self.empresa,
            nombre="Plantilla TEXTO",
            tipo="restaurante",
            activa=True,
        )

        self.bot = Bot.objects.create(
            empresa=self.empresa,
            plantilla=self.plantilla,
            nombre="Bot TEXTO",
            activo=True,
        )

        self.catalogo = Catalogo.objects.create(
            empresa=self.empresa,
            plantilla=self.plantilla,
            nombre="Menu TEXTO",
            moneda="MXN",
            activo=True,
        )

        self.categoria = CategoriaProducto.objects.create(
            catalogo=self.catalogo,
            nombre="Menú general",
            activa=True,
        )

        self.producto = Producto.objects.create(
            catalogo=self.catalogo,
            categoria=self.categoria,
            sku="TXT-001",
            nombre="Alitas",
            precio=Decimal("100.0000"),
            stock=Decimal("50.0000"),
            activo=True,
        )

        self.grupo_salsa = (
            GrupoModificadorProducto.objects.create(
                producto=self.producto,
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

        self.teriyaki = OpcionModificadorProducto.objects.create(
            grupo=self.grupo_salsa,
            nombre="Teriyaki",
            precio_adicional=Decimal("0.0000"),
            orden=2,
            activa=True,
        )

        self.agotada = OpcionModificadorProducto.objects.create(
            grupo=self.grupo_salsa,
            nombre="Habanero agotado",
            precio_adicional=Decimal("0.0000"),
            orden=3,
            activa=False,
        )

        self.grupo_extras = (
            GrupoModificadorProducto.objects.create(
                producto=self.producto,
                nombre="Extras",
                tipo=GrupoModificadorProducto.Tipo.EXTRA,
                obligatorio=False,
                minimo=0,
                maximo=3,
                orden=2,
                activo=True,
            )
        )

        self.queso = OpcionModificadorProducto.objects.create(
            grupo=self.grupo_extras,
            nombre="Queso",
            precio_adicional=Decimal("10.0000"),
            orden=1,
            activa=True,
        )

        self.tocino = OpcionModificadorProducto.objects.create(
            grupo=self.grupo_extras,
            nombre="Tocino",
            precio_adicional=Decimal("15.0000"),
            orden=2,
            activa=True,
        )

        self.url = reverse(
            "core:api_typebot_restaurante_"
            "producto_configurador_resolver"
        )

    def pedir(self, texto, *, grupo_indice=0, seleccionadas=""):
        return self.client.get(
            self.url,
            {
                "bot_id": self.bot.id,
                "producto_id": self.producto.id,
                "grupo_indice": grupo_indice,
                "texto": texto,
                "seleccionadas": seleccionadas,
            },
            HTTP_AUTHORIZATION="Bearer " + self.CLAVE,
        )

    def datos(self, respuesta):
        return json.loads(
            respuesta.content.decode("utf-8")
        )

    def test_01_numero_resuelve_opcion_del_grupo(self):

        datos = self.datos(
            self.pedir("1")
        )

        self.assertEqual(
            datos["resuelto"],
            "true",
        )

        self.assertEqual(
            datos["opcion_ids"],
            [self.bbq.id],
        )

    def test_02_nombre_resuelve_opcion(self):

        datos = self.datos(
            self.pedir("teriyaki")
        )

        self.assertEqual(
            datos["opcion_ids"],
            [self.teriyaki.id],
        )

    def test_03_opcion_inactiva_no_existe_para_el_cliente(self):

        datos = self.datos(
            self.pedir("Habanero agotado")
        )

        self.assertEqual(
            datos["resuelto"],
            "false",
        )

        self.assertEqual(
            datos["motivo"],
            "nombre_invalido",
        )

        # El número 3 tampoco existe: sólo hay 2 activas.
        self.assertEqual(
            self.datos(self.pedir("3"))["motivo"],
            "numero_invalido",
        )

    def test_04_opcion_de_otro_grupo_se_rechaza(self):

        # "Queso" pertenece al grupo de extras (índice 1).
        datos = self.datos(
            self.pedir("Queso")
        )

        self.assertEqual(
            datos["resuelto"],
            "false",
        )

        self.assertEqual(
            datos["motivo"],
            "nombre_invalido",
        )

    def test_05_extras_aceptan_varios_numeros(self):

        datos = self.datos(
            self.pedir(
                "1 y 2",
                grupo_indice=1,
            )
        )

        self.assertEqual(
            datos["resuelto"],
            "true",
        )

        self.assertEqual(
            datos["opcion_ids"],
            [
                self.queso.id,
                self.tocino.id,
            ],
        )

    def test_06_acumula_sin_duplicar(self):

        datos = self.datos(
            self.pedir(
                "2",
                grupo_indice=1,
                seleccionadas=f"{self.bbq.id},{self.queso.id}",
            )
        )

        self.assertEqual(
            datos["opcion_ids_acumuladas"],
            [
                self.bbq.id,
                self.queso.id,
                self.tocino.id,
            ],
        )

        repetida = self.datos(
            self.pedir(
                "1",
                grupo_indice=1,
                seleccionadas=f"{self.queso.id}",
            )
        )

        self.assertEqual(
            repetida["motivo"],
            "ya_elegida",
        )

    def test_07_sin_autorizacion_no_responde(self):

        respuesta = self.client.get(
            self.url,
            {
                "bot_id": self.bot.id,
                "producto_id": self.producto.id,
                "grupo_indice": 0,
                "texto": "1",
            },
        )

        self.assertEqual(
            respuesta.status_code,
            401,
        )

    def test_08_metodo_no_permitido(self):

        respuesta = self.client.post(
            self.url,
            HTTP_AUTHORIZATION="Bearer " + self.CLAVE,
        )

        self.assertEqual(
            respuesta.status_code,
            405,
        )

    def test_09_otro_bot_no_resuelve_este_producto(self):

        otra_empresa = Empresa.objects.create(
            nombre="Restaurante AJENO",
            rfc="RAJ010101AA1",
        )

        otra_plantilla = Plantilla.objects.create(
            empresa=otra_empresa,
            nombre="Plantilla AJENA",
            tipo="restaurante",
            activa=True,
        )

        otro_bot = Bot.objects.create(
            empresa=otra_empresa,
            plantilla=otra_plantilla,
            nombre="Bot AJENO",
            activo=True,
        )

        respuesta = self.client.get(
            self.url,
            {
                "bot_id": otro_bot.id,
                "producto_id": self.producto.id,
                "grupo_indice": 0,
                "texto": "1",
            },
            HTTP_AUTHORIZATION="Bearer " + self.CLAVE,
        )

        self.assertNotEqual(
            respuesta.status_code,
            200,
        )
