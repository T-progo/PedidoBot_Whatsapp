from datetime import timedelta

from django.contrib.auth import (
    get_user_model,
)
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Empresa,
    Licencia,
    Pedido,
    PerfilUsuario,
)


class RestaurantePanelListaUITests(
    TestCase
):

    def setUp(self):

        User = get_user_model()

        self.admin = (
            User.objects.create_superuser(
                username=
                    "r3-list-ui-admin",

                email=
                    "r3-list-ui@example.com",

                password=
                    "test-only-password",
            )
        )

        self.cliente_user = (
            User.objects.create_user(
                username=
                    "r3-list-ui-cliente",

                password=
                    "test-only-password",
            )
        )

        self.empresa = (
            Empresa.objects.create(
                nombre=
                    "Rest Lista UI TEST",

                rfc=
                    "RLU010101AA1",
            )
        )

        PerfilUsuario.objects.create(
            usuario=
                self.cliente_user,

            empresa=
                self.empresa,

            rol=
                PerfilUsuario
                .Rol
                .CLIENTE,

            activo=True,
        )

        hoy = timezone.localdate()

        Licencia.objects.create(
            empresa=
                self.empresa,

            nombre=
                "Licencia Lista UI TEST",

            estado=
                "activa",

            fecha_inicio=
                hoy
                -
                timedelta(
                    days=1
                ),

            fecha_fin=
                hoy
                +
                timedelta(
                    days=30
                ),
        )

        self.counter = 0

        self.client.force_login(
            self.admin
        )


    def pedido(
        self,
        *,
        estado,
        tipo_orden="domicilio",
        eta=25,
    ):

        self.counter += 1

        return Pedido.objects.create(
            empresa=
                self.empresa,

            numero=(
                "PED-LISTA-"
                +
                str(
                    self.counter
                ).zfill(4)
            ),

            estado=
                estado,

            tipo_orden=
                tipo_orden,

            tiempo_estimado_minutos=
                eta,

            moneda=
                "MXN",
        )


    def test_01_admin_preparando_domicilio_muestra_listo(
        self,
    ):

        pedido = self.pedido(
            estado="preparando",
        )

        response = self.client.get(
            reverse(
                "core:pedido_lista"
            )
        )

        self.assertContains(
            response,
            "A domicilio",
        )

        self.assertContains(
            response,
            "25 min",
        )

        self.assertContains(
            response,
            "Marcar listo",
        )

        self.assertContains(
            response,
            reverse(
                "core:pedido_estado_rapido",
                kwargs={
                    "pk":
                        pedido.pk,

                    "nuevo_estado":
                        "listo",
                },
            ),
        )


    def test_02_admin_legacy_preparando_conserva_enviado(
        self,
    ):

        pedido = self.pedido(
            estado="preparando",
            tipo_orden="",
            eta=None,
        )

        response = self.client.get(
            reverse(
                "core:pedido_lista"
            )
        )

        self.assertContains(
            response,
            "Despachar",
        )

        self.assertContains(
            response,
            reverse(
                "core:pedido_estado_rapido",
                kwargs={
                    "pk":
                        pedido.pk,

                    "nuevo_estado":
                        "enviado",
                },
            ),
        )


    def test_03_cliente_domicilio_muestra_listo(
        self,
    ):

        pedido = self.pedido(
            estado="preparando",
        )

        self.client.force_login(
            self.cliente_user
        )

        response = self.client.get(
            reverse(
                "core:cliente_pedido_lista"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "A domicilio",
        )

        self.assertContains(
            response,
            reverse(
                "core:cliente_pedido_estado_rapido",
                kwargs={
                    "pk":
                        pedido.pk,

                    "nuevo_estado":
                        "listo",
                },
            ),
        )


    def test_04_domicilio_listo_siguiente_en_camino(
        self,
    ):

        pedido = self.pedido(
            estado="listo",
            tipo_orden="domicilio",
        )

        response = self.client.get(
            reverse(
                "core:pedido_lista"
            )
        )

        self.assertContains(
            response,
            "En camino",
        )

        self.assertContains(
            response,
            reverse(
                "core:pedido_estado_rapido",
                kwargs={
                    "pk":
                        pedido.pk,

                    "nuevo_estado":
                        "en_camino",
                },
            ),
        )


    def test_05_para_llevar_listo_siguiente_entregado(
        self,
    ):

        pedido = self.pedido(
            estado="listo",
            tipo_orden=
                "para_llevar",
        )

        self.client.force_login(
            self.cliente_user
        )

        response = self.client.get(
            reverse(
                "core:cliente_pedido_lista"
            )
        )

        self.assertContains(
            response,
            "Para llevar",
        )

        self.assertContains(
            response,
            reverse(
                "core:cliente_pedido_estado_rapido",
                kwargs={
                    "pk":
                        pedido.pk,

                    "nuevo_estado":
                        "entregado",
                },
            ),
        )

        self.assertNotContains(
            response,
            (
                f"/mi-negocio/pedidos/"
                f"{pedido.pk}/estado/"
                "en_camino/"
            ),
        )
