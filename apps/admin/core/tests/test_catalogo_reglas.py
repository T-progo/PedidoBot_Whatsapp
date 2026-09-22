import json
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from openpyxl import Workbook

from core.forms import ProductoForm
from core.models import (
    Bot,
    Catalogo,
    CategoriaProducto,
    Empresa,
    GrupoModificadorProducto,
    OpcionModificadorProducto,
    Pedido,
    Plantilla,
    Producto,
)
from core.product_import import HEADERS, _decimal, validar_archivo_productos
from core.services.catalogo import (
    MENSAJE_PRECIO_CENTAVOS,
    precio_en_centavos,
    productos_vendibles,
)
from core.services.ia_prompt import construir_contexto_catalogo_ia
from core.views_api import _ia_productos_visuales_respuesta


# TNL-CATALOGO-REGLAS-V1
class PrecisionPrecioTests(SimpleTestCase):

    def test_precio_en_centavos(self):
        for valor in ("0", "12", "12.5", "12.50", "12.5000", Decimal("1499.9900")):
            with self.subTest(valor=valor):
                self.assertTrue(precio_en_centavos(valor))
        for valor in ("12.345", "0.001", Decimal("1499.4321"), "NaN", "Infinity", "abc", None):
            with self.subTest(valor=valor):
                self.assertFalse(precio_en_centavos(valor))

    def test_importador_rechaza_miles_ambiguos(self):
        for texto in ("1,500", "12,000", "1,234,567"):
            with self.subTest(texto=texto):
                with self.assertRaisesMessage(ValueError, "es ambiguo"):
                    _decimal(texto, field="precio", max_decimales=2)
                with self.assertRaisesMessage(ValueError, "es ambiguo"):
                    _decimal(texto, field="stock")

    def test_importador_precio_maximo_dos_decimales(self):
        for valor in ("12.345", "1.500", "12.5000", 12.345, "12,3456"):
            with self.subTest(valor=valor):
                with self.assertRaisesMessage(ValueError, "precio: máximo 2 decimales."):
                    _decimal(valor, field="precio", max_decimales=2)

    def test_importador_valores_validos_sin_redondeo(self):
        casos = {
            "1500": Decimal("1500.0000"),
            "85.50": Decimal("85.5000"),
            "12,5": Decimal("12.5000"),
            "12,50": Decimal("12.5000"),
            85: Decimal("85.0000"),
            85.5: Decimal("85.5000"),
        }
        for valor, esperado in casos.items():
            with self.subTest(valor=valor):
                self.assertEqual(_decimal(valor, field="precio", max_decimales=2), esperado)
        # El stock conserva sus 4 decimales.
        self.assertEqual(_decimal("1.2345", field="stock"), Decimal("1.2345"))

    def test_importador_ambos_separadores_sigue_rechazado(self):
        with self.assertRaisesMessage(ValueError, "usa un solo separador decimal"):
            _decimal("1,500.50", field="precio", max_decimales=2)


class _CatalogoBase(TestCase):

    def crear_empresa(self, nombre, rfc, tipo="restaurante"):
        empresa = Empresa.objects.create(nombre=nombre, rfc=rfc)
        plantilla = Plantilla.objects.create(
            empresa=empresa, nombre=f"Plantilla {nombre}", tipo=tipo, activa=True,
        )
        bot = Bot.objects.create(empresa=empresa, plantilla=plantilla, nombre=f"Bot {nombre}", activo=True)
        catalogo = Catalogo.objects.create(
            empresa=empresa, plantilla=plantilla, nombre=f"Menú {nombre}", moneda="MXN", activo=True,
        )
        return empresa, plantilla, bot, catalogo

    def producto(self, nombre, *, catalogo=None, categoria="default", stock="10", activo=True, imagen=True):
        return Producto.objects.create(
            catalogo=catalogo or self.catalogo,
            categoria=self.categoria if categoria == "default" else categoria,
            sku=nombre.upper().replace(" ", "-"),
            nombre=nombre,
            precio=Decimal("50.0000"),
            stock=Decimal(stock),
            unidad="pieza",
            imagen_principal=f"productos/test/{nombre.replace(' ', '_')}.webp" if imagen else "",
            activo=activo,
        )


class ProductoVendibleTests(_CatalogoBase):
    """Una sola regla para el menú, el detalle, el carrito y la IA."""

    def setUp(self):
        key = patch("core.views_api._leer_clave_api", return_value="catalogo-test-key")
        vida = patch("core.views_api._nl_api_empresa_operativa_error", return_value=None)
        key.start()
        vida.start()
        self.addCleanup(key.stop)
        self.addCleanup(vida.stop)
        self.auth = {"HTTP_AUTHORIZATION": "Bearer catalogo-test-key"}

        self.empresa, self.plantilla, self.bot, self.catalogo = self.crear_empresa("Tacos Norte", "TNO010101AA1")
        self.categoria = CategoriaProducto.objects.create(catalogo=self.catalogo, nombre="Tacos", orden=1, activa=True)
        self.cat_inactiva = CategoriaProducto.objects.create(catalogo=self.catalogo, nombre="Ocultos", orden=2, activa=False)
        self.cat_agotados = CategoriaProducto.objects.create(catalogo=self.catalogo, nombre="Agotados", orden=3, activa=True)

        # Otro catálogo de la misma empresa y plantilla, y uno inactivo.
        self.catalogo_b = Catalogo.objects.create(
            empresa=self.empresa, plantilla=self.plantilla, nombre="Bebidas", moneda="MXN", activo=True,
        )
        self.cat_b = CategoriaProducto.objects.create(catalogo=self.catalogo_b, nombre="Refrescos", orden=4, activa=True)
        self.catalogo_off = Catalogo.objects.create(
            empresa=self.empresa, plantilla=self.plantilla, nombre="Viejo", moneda="MXN", activo=False,
        )
        self.cat_off = CategoriaProducto.objects.create(catalogo=self.catalogo_off, nombre="Viejo", orden=5, activa=True)

        self.vendible = self.producto("Taco Pastor")
        # TNL-RESTAURANTE-DISPONIBILIDAD-V1: restaurante sin inventario
        # numérico; Agotado = inactivo.
        self.sin_stock = self.producto("Taco Suadero", stock="0")
        self.agotado = self.producto("Taco Lengua", categoria=self.cat_agotados, stock="0", activo=False)
        self.inactivo = self.producto("Taco Tripa", activo=False)
        # Grupo obligatorio sin opciones disponibles: el platillo no se puede armar.
        self.sin_opciones = self.producto("Taco Campechano")
        grupo = GrupoModificadorProducto.objects.create(
            producto=self.sin_opciones, nombre="Tortilla", obligatorio=True, minimo=1, maximo=1,
        )
        OpcionModificadorProducto.objects.create(grupo=grupo, nombre="Maíz", activa=False)
        self.en_cat_inactiva = self.producto("Taco Oculto", categoria=self.cat_inactiva)
        self.sin_categoria = self.producto("Taco Suelto", categoria=None)
        self.cat_otro_catalogo = self.producto("Taco Cruzado", categoria=self.cat_b)
        self.en_catalogo_off = self.producto("Taco Viejo", catalogo=self.catalogo_off, categoria=self.cat_off)

        _, _, _, catalogo_ajeno = self.crear_empresa("Otra Taquería", "OTR020202BB2")
        self.ajeno = self.producto(
            "Taco Ajeno",
            catalogo=catalogo_ajeno,
            categoria=CategoriaProducto.objects.create(catalogo=catalogo_ajeno, nombre="Tacos", activa=True),
        )
        self.no_vendibles = [
            self.agotado, self.inactivo, self.sin_opciones, self.en_cat_inactiva,
            self.sin_categoria, self.cat_otro_catalogo, self.en_catalogo_off, self.ajeno,
        ]

    def get(self, name, params):
        return self.client.get(reverse(f"core:{name}"), params, **self.auth)

    # --- regla ---------------------------------------------------------------

    def test_regla_restaurante(self):
        ids = set(
            productos_vendibles(
                empresa_id=self.empresa.id, plantilla_id=self.plantilla.id, restaurante=True,
            ).values_list("id", flat=True)
        )
        self.assertEqual(ids, {self.vendible.id, self.sin_stock.id})

    def test_regla_otros_giros_no_exige_categoria_ni_stock(self):
        ids = set(
            productos_vendibles(empresa_id=self.empresa.id, restaurante=False).values_list("id", flat=True)
        )
        self.assertEqual(
            ids,
            {self.vendible.id, self.sin_stock.id, self.sin_categoria.id, self.cat_otro_catalogo.id, self.sin_opciones.id},
        )

    def test_platillo_disponible_de_nuevo_al_reactivar_su_opcion(self):
        OpcionModificadorProducto.objects.filter(grupo__producto=self.sin_opciones).update(activa=True)
        ids = set(
            productos_vendibles(
                empresa_id=self.empresa.id, plantilla_id=self.plantilla.id, restaurante=True,
            ).values_list("id", flat=True)
        )
        self.assertIn(self.sin_opciones.id, ids)

    # --- menú ----------------------------------------------------------------

    def test_categorias_solo_con_productos_vendibles(self):
        response = self.get("api_typebot_restaurante_categorias", {"bot_id": self.bot.id})
        self.assertEqual(response.status_code, 200)
        nombres = [c["nombre"] for c in response.json()["categorias"]]
        # "Agotados" sólo tiene un producto agotado; "Refrescos" sólo el
        # producto cuya categoría es de otro catálogo.
        self.assertEqual(nombres, ["Tacos"])

    def test_productos_de_categoria_solo_vendibles(self):
        response = self.get(
            "api_typebot_restaurante_productos", {"bot_id": self.bot.id, "categoria_id": self.categoria.id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [str(i) for i in response.json()["producto_ids"]],
            [str(self.vendible.id), str(self.sin_stock.id)],
        )

    # --- detalle y carrito ---------------------------------------------------

    def test_detalle_rechaza_no_vendibles(self):
        ok = self.get("api_typebot_restaurante_producto_detalle", {"bot_id": self.bot.id, "producto_id": self.vendible.id})
        self.assertEqual(ok.status_code, 200)
        for producto in self.no_vendibles:
            with self.subTest(producto=producto.nombre):
                response = self.get(
                    "api_typebot_restaurante_producto_detalle", {"bot_id": self.bot.id, "producto_id": producto.id},
                )
                self.assertEqual(response.status_code, 404)

    def agregar(self, producto):
        return self.client.post(
            reverse("core:api_typebot_restaurante_pedido_producto_agregar"),
            data=json.dumps({"bot_id": self.bot.id, "producto_id": producto.id, "cantidad": "1", "opcion_ids": []}),
            content_type="application/json",
            **self.auth,
        )

    def test_carrito_rechaza_no_vendibles_sin_crear_pedido(self):
        for producto in self.no_vendibles:
            with self.subTest(producto=producto.nombre):
                self.assertEqual(self.agregar(producto).status_code, 404)
        self.assertFalse(Pedido.objects.exists())
        response = self.agregar(self.vendible)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["ok"])

    # --- IA ------------------------------------------------------------------

    def test_contexto_ia_restaurante_usa_la_regla(self):
        contexto = construir_contexto_catalogo_ia(bot=self.bot)
        self.assertIn("Taco Pastor", contexto)
        self.assertIn("Taco Suadero", contexto)
        for producto in self.no_vendibles:
            with self.subTest(producto=producto.nombre):
                self.assertNotIn(producto.nombre, contexto)

    def test_contexto_ia_otros_giros(self):
        empresa, _, bot, catalogo = self.crear_empresa("Abarrotes Sur", "ABS030303CC3", tipo="abarrotes")
        activa = CategoriaProducto.objects.create(catalogo=catalogo, nombre="Varios", activa=True)
        oculta = CategoriaProducto.objects.create(catalogo=catalogo, nombre="Oculta", activa=False)
        self.producto("Arroz Sin Categoria", catalogo=catalogo, categoria=None, stock="0")
        self.producto("Frijol Visible", catalogo=catalogo, categoria=activa)
        self.producto("Azucar Oculta", catalogo=catalogo, categoria=oculta)
        contexto = construir_contexto_catalogo_ia(bot=bot)
        self.assertIn("Arroz Sin Categoria", contexto)
        self.assertIn("Frijol Visible", contexto)
        self.assertNotIn("Azucar Oculta", contexto)

    def test_tarjetas_ia_solo_vendibles(self):
        todos = [self.vendible, self.sin_stock] + self.no_vendibles
        respuesta = "Te recomiendo: " + ", ".join(p.nombre for p in todos) + "."
        resultado = _ia_productos_visuales_respuesta(bot=self.bot, respuesta=respuesta)
        self.assertEqual(
            sorted(str(i) for i in resultado["producto_ids"]),
            sorted([str(self.vendible.id), str(self.sin_stock.id)]),
        )


class ValidacionPrecioCatalogoTests(_CatalogoBase):

    def setUp(self):
        _, _, _, self.catalogo = self.crear_empresa("Precios", "PRE040404DD4")
        # El formulario de restaurante exige la categoría general activa.
        self.categoria = CategoriaProducto.objects.create(catalogo=self.catalogo, nombre="Menú general", activa=True)

    def datos_form(self, precio):
        return {
            "catalogo": self.catalogo.id, "sku": "P-1", "nombre": "Torta", "descripcion": "",
            "precio": precio, "stock": "10", "unidad": "pieza", "identificador_externo": "", "activo": "on",
        }

    def test_formulario_rechaza_fracciones_de_centavo(self):
        form = ProductoForm(data=self.datos_form("12.345"))
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["precio"], [MENSAJE_PRECIO_CENTAVOS])

    def test_formulario_acepta_centavos(self):
        for precio in ("12", "12.5", "12.50"):
            with self.subTest(precio=precio):
                form = ProductoForm(data=self.datos_form(precio))
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(form.cleaned_data["precio"], Decimal(precio))

    def test_formulario_muestra_precio_exacto_si_tiene_mas_de_dos_decimales(self):
        widget = ProductoForm().fields["precio"].widget
        self.assertEqual(widget.format_value(Decimal("12.5000")), "12.50")
        self.assertEqual(widget.format_value(Decimal("12.3456")), "12.3456")

    def test_modelo_producto(self):
        producto = self.producto("Torta Cubana", imagen=False)
        producto.precio = Decimal("99.999")
        with self.assertRaises(ValidationError) as ctx:
            producto.full_clean()
        self.assertEqual(ctx.exception.message_dict["precio"], [MENSAJE_PRECIO_CENTAVOS])
        producto.precio = Decimal("99.99")
        producto.full_clean()

    def test_modelo_opcion_modificador(self):
        grupo = GrupoModificadorProducto.objects.create(
            producto=self.producto("Torta Ahogada", imagen=False), nombre="Salsa", obligatorio=False, minimo=0, maximo=1,
        )
        opcion = OpcionModificadorProducto(grupo=grupo, nombre="Extra picante", precio_adicional=Decimal("1.005"))
        with self.assertRaises(ValidationError) as ctx:
            opcion.full_clean()
        self.assertEqual(ctx.exception.message_dict["precio_adicional"], [MENSAJE_PRECIO_CENTAVOS])
        opcion.precio_adicional = Decimal("5.00")
        opcion.full_clean()

    def test_importacion_excel_rechaza_miles_ambiguos_y_subcentavos(self):
        libro = Workbook()
        hoja = libro.active
        hoja.title = "Productos"
        hoja.append(HEADERS)
        hoja.append(["A-1", "Mil quinientos", "", "1,500", "10", "pieza", "", "SI"])
        hoja.append(["A-2", "Subcentavo", "", "12.345", "10", "pieza", "", "SI"])
        hoja.append(["A-3", "Correcto", "", "85.50", "10", "pieza", "", "SI"])
        archivo = BytesIO()
        libro.save(archivo)
        archivo.seek(0)

        resultado = validar_archivo_productos(archivo, catalogo=self.catalogo)

        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["filas"], [])
        errores = " | ".join(resultado["errores_filas"])
        self.assertIn('Fila 2: precio: "1,500" es ambiguo', errores)
        self.assertIn("Fila 3: precio: máximo 2 decimales.", errores)
        self.assertNotIn("Fila 4", errores)
