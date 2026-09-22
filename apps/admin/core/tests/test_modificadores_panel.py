from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from core.models import (
    Bot,
    Catalogo,
    CategoriaProducto,
    Empresa,
    GrupoModificadorProducto,
    OpcionModificadorProducto,
    PerfilUsuario,
    Plantilla,
    Producto,
)


# TNL-MODIFICADORES-PANEL-V1
class ModificadoresPanelTests(TestCase):

    def setUp(self):
        self.empresa, self.producto = self.crear_restaurante("Tacos Uno", "TUN010101AA1")
        self.otra_empresa, self.producto_ajeno = self.crear_restaurante("Tacos Dos", "TDO020202BB2")

        self.grupo = GrupoModificadorProducto.objects.create(
            producto=self.producto, nombre="Salsa", tipo="modificador",
            obligatorio=True, minimo=1, maximo=1, orden=1, activo=True,
        )
        self.opcion = OpcionModificadorProducto.objects.create(
            grupo=self.grupo, nombre="Chipotle", precio_adicional=Decimal("5.00"), orden=1, activa=True,
        )
        self.grupo_ajeno = GrupoModificadorProducto.objects.create(
            producto=self.producto_ajeno, nombre="Salsa", obligatorio=False, minimo=0, maximo=1,
        )
        self.opcion_ajena = OpcionModificadorProducto.objects.create(
            grupo=self.grupo_ajeno, nombre="Verde", precio_adicional=Decimal("3.00"),
        )

        self.admin = self.crear_usuario("admin-mod", PerfilUsuario.Rol.ADMINISTRADOR)
        self.client.force_login(self.admin)

    def crear_restaurante(self, nombre, rfc):
        from datetime import timedelta

        from django.utils import timezone

        from core.models import Licencia

        empresa = Empresa.objects.create(nombre=nombre, rfc=rfc)
        hoy = timezone.localdate()
        Licencia.objects.create(
            empresa=empresa, nombre=f"Licencia {nombre}", estado="activa",
            fecha_inicio=hoy - timedelta(days=1), fecha_fin=hoy + timedelta(days=30),
        )
        plantilla = Plantilla.objects.create(
            empresa=empresa, nombre=f"Plantilla {nombre}", tipo="restaurante", activa=True,
        )
        Bot.objects.create(empresa=empresa, plantilla=plantilla, nombre=f"Bot {nombre}", activo=True)
        catalogo = Catalogo.objects.create(
            empresa=empresa, plantilla=plantilla, nombre="Menú", moneda="MXN", activo=True,
        )
        categoria = CategoriaProducto.objects.create(catalogo=catalogo, nombre="Tacos", activa=True)
        producto = Producto.objects.create(
            catalogo=catalogo, categoria=categoria, sku=f"SKU-{rfc}", nombre=f"Taco {nombre}",
            precio=Decimal("50.00"), stock=Decimal("10"), unidad="pieza", activo=True,
        )
        return empresa, producto

    def crear_usuario(self, username, rol, empresa=None):
        usuario = get_user_model().objects.create_user(username=username, password="clave-prueba")
        PerfilUsuario.objects.create(usuario=usuario, rol=rol, empresa=empresa)
        return usuario

    # --- urls ----------------------------------------------------------------

    def url_lista(self, producto=None):
        return reverse("core:producto_modificadores", args=[(producto or self.producto).pk])

    def url_grupo(self, nombre, grupo=None, producto=None):
        return reverse(f"core:producto_modificador_grupo_{nombre}",
                       args=[(producto or self.producto).pk] + ([] if grupo is None else [grupo.pk]))

    def url_opcion(self, nombre, grupo=None, opcion=None, producto=None):
        args = [(producto or self.producto).pk, (grupo or self.grupo).pk]
        if opcion is not None:
            args.append(opcion.pk)
        return reverse(f"core:producto_modificador_opcion_{nombre}", args=args)

    def datos_grupo(self, **cambios):
        datos = {"nombre": "Salsa", "tipo": "modificador", "obligatorio": "on",
                 "minimo": "1", "maximo": "1", "orden": "1", "activo": "on"}
        datos.update(cambios)
        return {k: v for k, v in datos.items() if v is not None}

    def datos_opcion(self, **cambios):
        datos = {"nombre": "Chipotle", "precio_adicional": "5.00", "orden": "1", "activa": "on"}
        datos.update(cambios)
        return {k: v for k, v in datos.items() if v is not None}

    # --- permisos y pertenencia -----------------------------------------------

    def test_requiere_sesion_y_rol(self):
        anonimo = Client()
        respuesta = anonimo.get(self.url_lista())
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta["Location"].startswith("/login/"))

        for rol in (PerfilUsuario.Rol.CLIENTE, PerfilUsuario.Rol.OPERADOR):
            with self.subTest(rol=rol):
                otro = Client()
                otro.force_login(self.crear_usuario(f"user-{rol}", rol, empresa=self.empresa))
                self.assertEqual(otro.get(self.url_lista()).status_code, 403)
                self.assertEqual(otro.post(self.url_grupo("crear"), self.datos_grupo()).status_code, 403)

    def test_no_se_puede_tocar_lo_de_otro_producto(self):
        # Grupo y opción de otra empresa, pedidos desde este producto.
        rutas = [
            (self.url_grupo("editar", grupo=self.grupo_ajeno), True),
            (self.url_grupo("estado", grupo=self.grupo_ajeno), False),
            (self.url_opcion("crear", grupo=self.grupo_ajeno), True),
            (self.url_opcion("editar", grupo=self.grupo_ajeno, opcion=self.opcion_ajena), True),
            (self.url_opcion("estado", grupo=self.grupo_ajeno, opcion=self.opcion_ajena), False),
        ]
        for ruta, admite_get in rutas:
            with self.subTest(ruta=ruta):
                if admite_get:
                    self.assertEqual(self.client.get(ruta).status_code, 404)
                self.assertEqual(self.client.post(ruta, self.datos_grupo()).status_code, 404)

        # Una opción de otro grupo del mismo producto tampoco.
        otro_grupo = GrupoModificadorProducto.objects.create(
            producto=self.producto, nombre="Extras", obligatorio=False, minimo=0, maximo=2,
        )
        ruta = self.url_opcion("editar", grupo=otro_grupo, opcion=self.opcion)
        self.assertEqual(self.client.get(ruta).status_code, 404)

        self.grupo_ajeno.refresh_from_db()
        self.opcion_ajena.refresh_from_db()
        self.assertTrue(self.grupo_ajeno.activo)
        self.assertTrue(self.opcion_ajena.activa)

    def test_producto_inexistente(self):
        self.assertEqual(
            self.client.get(reverse("core:producto_modificadores", args=[999999])).status_code, 404,
        )

    # --- pantalla --------------------------------------------------------------

    def test_pantalla_muestra_grupos_y_opciones(self):
        respuesta = self.client.get(self.url_lista())
        self.assertEqual(respuesta.status_code, 200)
        html = respuesta.content.decode()
        for texto in ("Salsa", "Obligatorio", "Mínimo 1", "Máximo 1", "Activo",
                      "Chipotle", "5.00", "Disponible", self.producto.nombre):
            with self.subTest(texto=texto):
                self.assertIn(texto, html)
        self.assertIn(self.url_grupo("editar", grupo=self.grupo), html)
        self.assertIn("Marcar agotada", html)
        self.assertNotIn(self.grupo_ajeno.nombre + "</strong>", html)

    def test_lista_de_productos_enlaza_modificadores(self):
        respuesta = self.client.get(reverse("core:producto_lista"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(self.url_lista(), respuesta.content.decode())

    # --- grupos ----------------------------------------------------------------

    def test_crear_grupo(self):
        respuesta = self.client.post(
            self.url_grupo("crear"),
            self.datos_grupo(nombre="Término", minimo="1", maximo="2", orden="2"),
        )
        self.assertRedirects(respuesta, self.url_lista())
        grupo = GrupoModificadorProducto.objects.get(producto=self.producto, nombre="Término")
        self.assertEqual((grupo.minimo, grupo.maximo, grupo.orden), (1, 2, 2))
        self.assertTrue(grupo.obligatorio)
        self.assertTrue(grupo.activo)

    def test_editar_grupo(self):
        respuesta = self.client.post(
            self.url_grupo("editar", grupo=self.grupo),
            self.datos_grupo(nombre="Salsa de la casa", obligatorio=None, minimo="0", maximo="3"),
        )
        self.assertRedirects(respuesta, self.url_lista())
        self.grupo.refresh_from_db()
        self.assertEqual(self.grupo.nombre, "Salsa de la casa")
        self.assertFalse(self.grupo.obligatorio)
        self.assertEqual((self.grupo.minimo, self.grupo.maximo), (0, 3))

    def test_reglas_de_grupo(self):
        casos = [
            ({"minimo": "2", "maximo": "1"}, "maximo", "El máximo no puede ser menor que el mínimo."),
            ({"maximo": "0"}, "maximo", "El máximo debe ser al menos 1."),
            ({"obligatorio": "on", "minimo": "0"}, "minimo", "Un grupo obligatorio necesita un mínimo de 1 o más."),
        ]
        for cambios, campo, mensaje in casos:
            with self.subTest(**cambios):
                respuesta = self.client.post(self.url_grupo("crear"), self.datos_grupo(nombre="Prueba", **cambios))
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(respuesta.context["form"].errors[campo], [mensaje])
        self.assertFalse(GrupoModificadorProducto.objects.filter(nombre="Prueba").exists())

    def test_nombre_de_grupo_repetido(self):
        respuesta = self.client.post(self.url_grupo("crear"), self.datos_grupo(nombre="Salsa"))
        self.assertEqual(
            respuesta.context["form"].errors["nombre"],
            ["Este producto ya tiene un grupo con ese nombre."],
        )
        # El mismo nombre sí puede existir en otro producto. Administración
        # atiende a todas las empresas, como en el resto del panel.
        self.assertRedirects(
            self.client.post(
                self.url_grupo("crear", producto=self.producto_ajeno),
                self.datos_grupo(nombre="Otra salsa"),
            ),
            self.url_lista(producto=self.producto_ajeno),
        )

    def test_activar_y_desactivar_grupo(self):
        respuesta = self.client.post(self.url_grupo("estado", grupo=self.grupo))
        self.assertRedirects(respuesta, self.url_lista())
        self.grupo.refresh_from_db()
        self.assertFalse(self.grupo.activo)

        self.client.post(self.url_grupo("estado", grupo=self.grupo))
        self.grupo.refresh_from_db()
        self.assertTrue(self.grupo.activo)

        self.assertEqual(self.client.get(self.url_grupo("estado", grupo=self.grupo)).status_code, 405)

    # --- opciones ---------------------------------------------------------------

    def test_crear_y_editar_opcion(self):
        respuesta = self.client.post(
            self.url_opcion("crear"), self.datos_opcion(nombre="Habanero", precio_adicional="7.50", orden="2"),
        )
        self.assertRedirects(respuesta, self.url_lista())
        opcion = OpcionModificadorProducto.objects.get(grupo=self.grupo, nombre="Habanero")
        self.assertEqual(opcion.precio_adicional, Decimal("7.50"))
        self.assertEqual(opcion.orden, 2)

        respuesta = self.client.post(
            self.url_opcion("editar", opcion=opcion), self.datos_opcion(nombre="Habanero", precio_adicional="8"),
        )
        self.assertRedirects(respuesta, self.url_lista())
        opcion.refresh_from_db()
        self.assertEqual(opcion.precio_adicional, Decimal("8"))

    def test_precio_de_opcion_con_mas_de_dos_decimales(self):
        respuesta = self.client.post(
            self.url_opcion("crear"), self.datos_opcion(nombre="Ajo", precio_adicional="5.005"),
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            respuesta.context["form"].errors["precio_adicional"],
            ["El precio admite máximo 2 decimales (centavos)."],
        )
        self.assertFalse(OpcionModificadorProducto.objects.filter(nombre="Ajo").exists())

    def test_precio_de_opcion_negativo(self):
        respuesta = self.client.post(
            self.url_opcion("crear"), self.datos_opcion(nombre="Ajo", precio_adicional="-1.00"),
        )
        self.assertEqual(
            respuesta.context["form"].errors["precio_adicional"],
            ["El precio adicional no puede ser negativo."],
        )

    def test_marcar_opcion_agotada_y_disponible(self):
        respuesta = self.client.post(self.url_opcion("estado", opcion=self.opcion))
        self.assertRedirects(respuesta, self.url_lista())
        self.opcion.refresh_from_db()
        self.assertFalse(self.opcion.activa)

        self.client.post(self.url_opcion("estado", opcion=self.opcion))
        self.opcion.refresh_from_db()
        self.assertTrue(self.opcion.activa)

        self.assertEqual(self.client.get(self.url_opcion("estado", opcion=self.opcion)).status_code, 405)


# TNL-MODIFICADORES-PANEL-V1
class ModificadoresPanelYMenuTests(TestCase):
    """Lo que el panel cambia se refleja en el menú y en el carrito."""

    def setUp(self):
        from unittest.mock import patch

        key = patch("core.views_api._leer_clave_api", return_value="panel-menu-key")
        vida = patch("core.views_api._nl_api_empresa_operativa_error", return_value=None)
        key.start()
        vida.start()
        self.addCleanup(key.stop)
        self.addCleanup(vida.stop)
        self.auth = {"HTTP_AUTHORIZATION": "Bearer panel-menu-key"}

        self.empresa = Empresa.objects.create(nombre="Alitas Panel", rfc="ALP010101AA1")
        self.plantilla = Plantilla.objects.create(
            empresa=self.empresa, nombre="Restaurante", tipo="restaurante", activa=True,
        )
        self.bot = Bot.objects.create(
            empresa=self.empresa, plantilla=self.plantilla, nombre="Bot", activo=True,
        )
        catalogo = Catalogo.objects.create(
            empresa=self.empresa, plantilla=self.plantilla, nombre="Menú", moneda="MXN", activo=True,
        )
        categoria = CategoriaProducto.objects.create(catalogo=catalogo, nombre="Alitas", activa=True)
        self.producto = Producto.objects.create(
            catalogo=catalogo, categoria=categoria, sku="ALI-1", nombre="Alitas",
            precio=Decimal("100.00"), stock=Decimal("5"), unidad="pieza", activo=True,
        )
        self.grupo = GrupoModificadorProducto.objects.create(
            producto=self.producto, nombre="Salsa", obligatorio=True, minimo=1, maximo=1, activo=True,
        )
        self.opcion = OpcionModificadorProducto.objects.create(
            grupo=self.grupo, nombre="BBQ", precio_adicional=Decimal("5.00"), activa=True,
        )
        usuario = get_user_model().objects.create_user(username="admin-menu", password="clave-prueba")
        PerfilUsuario.objects.create(usuario=usuario, rol=PerfilUsuario.Rol.ADMINISTRADOR)
        self.client.force_login(usuario)

    def detalle_api(self):
        return self.client.get(
            reverse("core:api_typebot_restaurante_producto_detalle"),
            {"bot_id": self.bot.id, "producto_id": self.producto.id},
            **self.auth,
        )

    def test_opcion_agotada_desde_el_panel_desaparece_del_menu(self):
        self.assertEqual(self.detalle_api().status_code, 200)

        self.client.post(reverse(
            "core:producto_modificador_opcion_estado",
            args=[self.producto.pk, self.grupo.pk, self.opcion.pk],
        ))

        # Grupo obligatorio sin opciones disponibles: el producto queda agotado.
        self.assertEqual(self.detalle_api().status_code, 404)

        self.client.post(reverse(
            "core:producto_modificador_opcion_estado",
            args=[self.producto.pk, self.grupo.pk, self.opcion.pk],
        ))
        self.assertEqual(self.detalle_api().status_code, 200)

    def test_opcion_nueva_desde_el_panel_se_ofrece_con_su_precio(self):
        self.client.post(
            reverse("core:producto_modificador_opcion_crear", args=[self.producto.pk, self.grupo.pk]),
            {"nombre": "Mango habanero", "precio_adicional": "12.50", "orden": "2", "activa": "on"},
        )
        datos = self.detalle_api().json()
        opciones = [o for g in datos["grupos"] for o in g["opciones"]]
        self.assertIn(("Mango habanero", "12.50"), [(o["nombre"], o["precio_adicional"]) for o in opciones])
