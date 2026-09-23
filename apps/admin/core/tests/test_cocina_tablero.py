"""
Tablero de cocina (TNL-COCINA-TABLERO-V1).

Reutiliza el motor de estados existente: aquí sólo se prueba
qué ve la cocina y que las acciones respeten ese motor.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Catalogo,
    ConfiguracionRestaurante,
    Empresa,
    GrupoModificadorProducto,
    Licencia,
    OpcionModificadorProducto,
    Pedido,
    PerfilUsuario,
    Producto,
)
from core.services.pedidos import (
    agregar_producto_a_pedido,
    agregar_producto_configurado_a_pedido,
    crear_pedido,
)


class CocinaTableroTests(TestCase):

    def setUp(self):

        self.empresa = Empresa.objects.create(
            nombre="Restaurante COCINA",
            rfc="RCO010101AA1",
        )

        self.otra_empresa = Empresa.objects.create(
            nombre="Restaurante VECINO",
            rfc="RVE010101AA1",
        )

        for empresa in (self.empresa, self.otra_empresa):

            # La licencia se evalúa con la fecha local de la
            # app, no con la UTC: se ancla un día antes.
            hoy = timezone.localdate()

            Licencia.objects.create(
                empresa=empresa,
                nombre=f"Licencia {empresa.nombre}",
                estado="activa",
                fecha_inicio=hoy - timedelta(days=1),
                fecha_fin=hoy + timedelta(days=30),
            )

            ConfiguracionRestaurante.objects.create(
                empresa=empresa,
                costo_envio_fijo=Decimal("0.0000"),
                envio_gratis_desde=Decimal("0.0000"),
                tiempo_estimado_minutos=20,
                habilitada=True,
            )

        self.catalogo = Catalogo.objects.create(
            empresa=self.empresa,
            nombre="Menu COCINA",
            moneda="MXN",
            activo=True,
        )

        self.alitas = Producto.objects.create(
            catalogo=self.catalogo,
            sku="COC-001",
            nombre="Alitas",
            precio=Decimal("100.0000"),
            stock=Decimal("100.0000"),
            activo=True,
        )

        self.refresco = Producto.objects.create(
            catalogo=self.catalogo,
            sku="COC-002",
            nombre="Refresco",
            precio=Decimal("20.0000"),
            stock=Decimal("100.0000"),
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

        self.teriyaki = OpcionModificadorProducto.objects.create(
            grupo=self.grupo_extras,
            nombre="Teriyaki",
            precio_adicional=Decimal("5.0000"),
            orden=1,
            activa=True,
        )

        self.buffalo = OpcionModificadorProducto.objects.create(
            grupo=self.grupo_extras,
            nombre="Buffalo hot",
            precio_adicional=Decimal("5.0000"),
            orden=2,
            activa=True,
        )

        User = get_user_model()

        # El tablero usa los mismos roles que la pantalla de
        # pedidos: cliente (su empresa) y administrador.
        self.encargado = User.objects.create_user(
            username="encargado",
            password="cocina-123",
        )

        PerfilUsuario.objects.create(
            usuario=self.encargado,
            empresa=self.empresa,
            rol=PerfilUsuario.Rol.CLIENTE,
            activo=True,
        )

        self.operador = User.objects.create_user(
            username="operador",
            password="cocina-123",
        )

        PerfilUsuario.objects.create(
            usuario=self.operador,
            empresa=self.empresa,
            rol=PerfilUsuario.Rol.OPERADOR,
            activo=True,
        )

        self.url = reverse(
            "core:cliente_cocina_tablero"
        )

    # ------------------------------------------------------------------
    # Datos
    # ------------------------------------------------------------------

    def crear_pedido_restaurante(
        self,
        *,
        empresa=None,
        estado="confirmado",
        con_opciones=True,
        tipo_orden="comedor",
    ):

        empresa = empresa or self.empresa

        pedido = crear_pedido(
            empresa_id=empresa.id,
            moneda="MXN",
            cliente_nombre="Cliente COCINA",
            cliente_telefono="3312345678",
            cliente_email="",
            direccion_entrega="",
            notas="Sin cebolla",
        )

        if empresa == self.empresa:

            if con_opciones:

                agregar_producto_configurado_a_pedido(
                    pedido_id=pedido.id,
                    producto_id=self.alitas.id,
                    cantidad="2.0000",
                    seleccion_opciones=[
                        self.bbq.id,
                        self.teriyaki.id,
                        self.buffalo.id,
                    ],
                )

            else:

                agregar_producto_a_pedido(
                    pedido_id=pedido.id,
                    producto_id=self.refresco.id,
                    cantidad="1.0000",
                )

        Pedido.objects.filter(
            pk=pedido.pk
        ).update(
            estado=estado,
            tipo_orden=tipo_orden,
        )

        pedido.refresh_from_db()

        return pedido

    def entrar(self):
        self.client.force_login(
            self.encargado
        )

    # ------------------------------------------------------------------
    # Acceso
    # ------------------------------------------------------------------

    def test_01_anonimo_no_entra(self):

        respuesta = self.client.get(
            self.url
        )

        self.assertEqual(
            respuesta.status_code,
            302,
        )

        self.assertIn(
            "/login/",
            respuesta["Location"],
        )

    def test_02_rol_sin_permiso_no_entra(self):

        self.client.force_login(
            self.operador
        )

        respuesta = self.client.get(
            self.url
        )

        self.assertEqual(
            respuesta.status_code,
            403,
        )

    def test_02b_encargado_autorizado_entra(self):

        self.entrar()

        respuesta = self.client.get(
            self.url
        )

        self.assertEqual(
            respuesta.status_code,
            200,
        )

        self.assertContains(
            respuesta,
            "Tablero de preparación",
        )

    def test_03_solo_pedidos_de_su_empresa(self):

        propio = self.crear_pedido_restaurante()

        ajeno = self.crear_pedido_restaurante(
            empresa=self.otra_empresa,
        )

        self.entrar()

        respuesta = self.client.get(
            self.url
        )

        # El número se reinicia por empresa, así que se
        # compara el id para detectar fugas entre negocios.
        ids = [
            ticket["pedido"].id
            for ticket
            in respuesta.context["por_preparar"]
        ]

        self.assertIn(
            propio.id,
            ids,
        )

        self.assertNotIn(
            ajeno.id,
            ids,
        )

    # ------------------------------------------------------------------
    # Contenido del ticket
    # ------------------------------------------------------------------

    def test_04_ticket_muestra_productos_modificadores_y_extras(self):

        pedido = self.crear_pedido_restaurante()

        self.entrar()

        respuesta = self.client.get(
            self.url
        )

        self.assertContains(
            respuesta,
            pedido.numero,
        )

        self.assertContains(
            respuesta,
            "Alitas",
        )

        self.assertContains(
            respuesta,
            "Salsa:",
        )

        self.assertContains(
            respuesta,
            "BBQ",
        )

        self.assertContains(
            respuesta,
            "Teriyaki, Buffalo hot",
        )

        self.assertContains(
            respuesta,
            "Sin cebolla",
        )

        self.assertContains(
            respuesta,
            "Comedor",
        )

    def test_05_linea_sin_modificadores_se_muestra_igual(self):

        self.crear_pedido_restaurante(
            con_opciones=False,
        )

        self.entrar()

        respuesta = self.client.get(
            self.url
        )

        ticket = respuesta.context[
            "por_preparar"
        ][0]

        self.assertEqual(
            ticket["lineas"][0]["grupos"],
            [],
        )

        self.assertContains(
            respuesta,
            "Refresco",
        )

    # ------------------------------------------------------------------
    # Estados
    # ------------------------------------------------------------------

    def test_06_transicion_valida_confirmado_a_preparando(self):

        pedido = self.crear_pedido_restaurante()

        self.entrar()

        respuesta = self.client.post(
            reverse(
                "core:cliente_pedido_estado_rapido",
                args=[
                    pedido.pk,
                    "preparando",
                ],
            ),
            {
                "origen": "cocina",
            },
        )

        self.assertEqual(
            respuesta.status_code,
            302,
        )

        self.assertEqual(
            respuesta["Location"],
            self.url,
        )

        pedido.refresh_from_db()

        self.assertEqual(
            pedido.estado,
            "preparando",
        )

    def test_07_transicion_invalida_se_rechaza(self):

        pedido = self.crear_pedido_restaurante()

        self.entrar()

        self.client.post(
            reverse(
                "core:cliente_pedido_estado_rapido",
                args=[
                    pedido.pk,
                    "listo",
                ],
            ),
            {
                "origen": "cocina",
            },
        )

        pedido.refresh_from_db()

        self.assertEqual(
            pedido.estado,
            "confirmado",
        )

    def test_08_transicion_repetida_es_segura(self):

        pedido = self.crear_pedido_restaurante(
            estado="preparando",
        )

        self.entrar()

        for _ in range(2):

            self.client.post(
                reverse(
                    "core:cliente_pedido_estado_rapido",
                    args=[
                        pedido.pk,
                        "listo",
                    ],
                ),
                {
                    "origen": "cocina",
                },
            )

        pedido.refresh_from_db()

        self.assertEqual(
            pedido.estado,
            "listo",
        )

        self.assertEqual(
            pedido.estado_eventos.filter(
                estado_nuevo="listo",
            ).count(),
            1,
        )

    def test_09_no_se_puede_cambiar_pedido_de_otra_empresa(self):

        ajeno = self.crear_pedido_restaurante(
            empresa=self.otra_empresa,
        )

        self.entrar()

        respuesta = self.client.post(
            reverse(
                "core:cliente_pedido_estado_rapido",
                args=[
                    ajeno.pk,
                    "preparando",
                ],
            ),
            {
                "origen": "cocina",
            },
        )

        self.assertEqual(
            respuesta.status_code,
            404,
        )

        ajeno.refresh_from_db()

        self.assertEqual(
            ajeno.estado,
            "confirmado",
        )

    def test_10_entregados_y_cancelados_no_son_tickets(self):

        activo = self.crear_pedido_restaurante()

        entregado = self.crear_pedido_restaurante(
            estado="entregado",
        )

        cancelado = self.crear_pedido_restaurante(
            estado="cancelado",
        )

        carrito = self.crear_pedido_restaurante(
            estado="carrito",
        )

        self.entrar()

        respuesta = self.client.get(
            self.url
        )

        self.assertEqual(
            respuesta.context["total_tickets"],
            1,
        )

        self.assertContains(
            respuesta,
            activo.numero,
        )

        for fuera in (
            entregado,
            cancelado,
            carrito,
        ):
            self.assertNotContains(
                respuesta,
                fuera.numero,
            )

    def test_11_pedido_listo_no_ofrece_accion_de_cocina(self):

        self.crear_pedido_restaurante(
            estado="listo",
        )

        self.entrar()

        respuesta = self.client.get(
            self.url
        )

        ticket = respuesta.context[
            "listos"
        ][0]

        self.assertEqual(
            ticket["siguiente_estado"],
            "",
        )

        self.assertContains(
            respuesta,
            "La entrega se registra desde Pedidos.",
        )

    def test_12_pedido_no_restaurante_no_aparece(self):

        self.crear_pedido_restaurante(
            tipo_orden="",
        )

        self.entrar()

        respuesta = self.client.get(
            self.url
        )

        self.assertEqual(
            respuesta.context["total_tickets"],
            0,
        )
