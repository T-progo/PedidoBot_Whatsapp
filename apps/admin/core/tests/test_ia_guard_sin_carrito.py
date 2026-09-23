"""
Guard de salida IA sin carrito (TNL-IA-SIN-CARRITO-GUARD-V1).

La IA no toma pedidos: si no hay carrito real y su respuesta
habla de pagos, métodos inexistentes o da por registrado un
pedido, se descarta y se manda al menú real.
"""

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone

from core.models import (
    Bot,
    Catalogo,
    ConfiguracionRestaurante,
    Empresa,
    Licencia,
    Plantilla,
    Producto,
)
from core.services.pedidos import (
    agregar_producto_a_pedido,
    crear_pedido,
)
from core.views_api import _ia_guardrail_salida_pago_chango


class IaGuardSinCarritoTests(TestCase):

    def setUp(self):

        self.empresa = Empresa.objects.create(
            nombre="Restaurante IA",
            rfc="RIA010101AA1",
        )

        hoy = timezone.localdate()

        Licencia.objects.create(
            empresa=self.empresa,
            nombre="Licencia IA",
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
            nombre="Plantilla IA",
            tipo="restaurante",
            activa=True,
        )

        self.bot = Bot.objects.create(
            empresa=self.empresa,
            plantilla=self.plantilla,
            nombre="Bot IA",
            activo=True,
        )

        self.catalogo = Catalogo.objects.create(
            empresa=self.empresa,
            nombre="Menu IA",
            moneda="MXN",
            activo=True,
        )

        self.producto = Producto.objects.create(
            catalogo=self.catalogo,
            sku="IA-001",
            nombre="Alitas",
            precio=Decimal("100.0000"),
            stock=Decimal("50.0000"),
            activo=True,
        )

    def guard(self, respuesta, *, carrito_token=""):
        return _ia_guardrail_salida_pago_chango(
            bot=self.bot,
            respuesta=respuesta,
            carrito_token=carrito_token,
        )

    def crear_carrito_real(self):

        pedido = crear_pedido(
            empresa_id=self.empresa.id,
            moneda="MXN",
            cliente_nombre="Cliente IA",
            cliente_telefono="3312345678",
            cliente_email="",
            direccion_entrega="",
            notas="",
        )

        agregar_producto_a_pedido(
            pedido_id=pedido.id,
            producto_id=self.producto.id,
            cantidad="1.0000",
        )

        # Mismo formato que emite la API: el token del flujo
        # es r:<bot_id>:<32 hex> y se guarda con prefijo.
        self.carrito_token = f"r:{self.bot.id}:{uuid4().hex}"

        pedido.identificador_externo = (
            "typebot:" + self.carrito_token
        )

        pedido.save(
            update_fields=[
                "identificador_externo",
            ]
        )

        pedido.refresh_from_db()

        return pedido

    # ------------------------------------------------------------------
    # Sin carrito
    # ------------------------------------------------------------------

    def test_01_sin_carrito_pregunta_de_pago_va_al_menu(self):

        resultado = self.guard(
            "¿Cómo deseas pagar? Aceptamos efectivo o tarjeta."
        )

        self.assertIsNotNone(resultado)

        self.assertEqual(
            resultado["ia_accion"],
            "mostrar_categorias",
        )

        self.assertIn(
            "menú",
            resultado["respuesta"],
        )

    def test_02_sin_carrito_transferencia_no_se_ofrece(self):

        resultado = self.guard(
            "Puedo enviarte los datos de transferencia "
            "bancaria o un enlace de pago."
        )

        self.assertIsNotNone(resultado)

        self.assertEqual(
            resultado["ia_accion"],
            "mostrar_categorias",
        )

        texto = resultado["respuesta"].lower()

        for prohibido in (
            "transferencia",
            "enlace de pago",
            "clabe",
            "spei",
        ):
            self.assertNotIn(
                prohibido,
                texto,
            )

    def test_03_sin_carrito_no_puede_dar_pedido_por_registrado(self):

        for respuesta in (
            "Listo, tu pedido quedó registrado.",
            "Tu pedido es 2 alitas, subtotal $155.",
            "Ya tomé tu pedido, pasa por él en 20 minutos.",
        ):

            resultado = self.guard(respuesta)

            self.assertIsNotNone(
                resultado,
                respuesta,
            )

            self.assertEqual(
                resultado["ia_accion"],
                "mostrar_categorias",
                respuesta,
            )

    def test_04_token_sin_carrito_real_se_trata_como_sin_carrito(self):

        resultado = self.guard(
            "¿Prefieres pagar con tarjeta?",
            carrito_token="token-que-no-existe",
        )

        self.assertIsNotNone(resultado)

        self.assertEqual(
            resultado["ia_accion"],
            "mostrar_categorias",
        )

    # ------------------------------------------------------------------
    # Con carrito real: comportamiento vigente
    # ------------------------------------------------------------------

    def test_05_con_carrito_real_sigue_cerrando_el_pedido(self):

        pedido = self.crear_carrito_real()

        resultado = self.guard(
            "¿Cómo deseas pagar? Tenemos efectivo.",
            carrito_token=self.carrito_token,
        )

        self.assertEqual(
            resultado,
            {
                "ia_accion":
                    "finalizar_pedido_actual",
            },
        )

    def test_06_con_carrito_real_sin_tema_de_pago_no_interviene(self):

        pedido = self.crear_carrito_real()

        self.assertIsNone(
            self.guard(
                "Nuestras alitas vienen en porciones de 6, "
                "10 y 20 piezas.",
                carrito_token=self.carrito_token,
            )
        )

    # ------------------------------------------------------------------
    # Conversación normal
    # ------------------------------------------------------------------

    def test_07_conversacion_normal_no_se_toca(self):

        for respuesta in (
            "Abrimos de lunes a domingo de 1 a 10 de la noche.",
            "Estamos en avenida Juárez 123, junto a la plaza.",
            "Las alitas más pedidas son las BBQ y las búfalo.",
        ):
            self.assertIsNone(
                self.guard(respuesta),
                respuesta,
            )

    def test_08_otra_plantilla_no_se_ve_afectada(self):

        self.plantilla.tipo = "abarrotes"
        self.plantilla.save(
            update_fields=[
                "tipo",
            ]
        )

        self.bot.refresh_from_db()

        self.assertIsNone(
            self.guard(
                "¿Deseas pagar con transferencia?"
            )
        )
