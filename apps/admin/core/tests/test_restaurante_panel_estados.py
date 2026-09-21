from datetime import timedelta
from unittest.mock import patch

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
    PedidoEstadoEvento,
    PerfilUsuario,
)


class RestaurantePanelEstadosTests(
    TestCase
):

    def setUp(self):

        User = get_user_model()

        self.admin = (
            User.objects.create_superuser(
                username=
                    "r3-panel-admin",

                email=
                    "r3-panel@example.com",

                password=
                    "test-only-password",
            )
        )

        self.empresa = (
            Empresa.objects.create(
                nombre=
                    "Rest Panel TEST",

                rfc=
                    "RPT010101AA1",
            )
        )

        self.otra_empresa = (
            Empresa.objects.create(
                nombre=
                    "Otra Empresa Panel",

                rfc=
                    "RPT020202BB2",
            )
        )

        hoy = timezone.localdate()

        # El middleware productivo exige que
        # un usuario CLIENTE tenga empresa activa
        # y licencia activa + vigente.
        Licencia.objects.create(
            empresa=
                self.empresa,

            nombre=
                "Licencia TEST R3 Panel",

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
        tipo_orden="",
        empresa=None,
    ):

        self.counter += 1

        return Pedido.objects.create(
            empresa=(
                empresa
                or
                self.empresa
            ),

            numero=(
                "PED-PANEL-"
                +
                str(
                    self.counter
                ).zfill(4)
            ),

            estado=
                estado,

            tipo_orden=
                tipo_orden,

            moneda=
                "MXN",
        )


    def post_estado(
        self,
        pedido,
        nuevo_estado,
        *,
        cliente=False,
    ):

        name = (
            "cliente_pedido_estado_rapido"
            if cliente
            else "pedido_estado_rapido"
        )

        return self.client.post(
            reverse(
                "core:" + name,
                kwargs={
                    "pk":
                        pedido.pk,

                    "nuevo_estado":
                        nuevo_estado,
                },
            ),
            {
                "origen":
                    "detalle",
            },
        )


    def test_01_detalle_domicilio_expone_next_listo(
        self,
    ):

        pedido = self.pedido(
            estado="preparando",
            tipo_orden="domicilio",
        )

        response = self.client.get(
            reverse(
                "core:pedido_detalle",
                kwargs={
                    "pk":
                        pedido.pk,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTrue(
            response.context[
                "es_pedido_restaurante"
            ]
        )

        self.assertEqual(
            response.context[
                "siguiente_estado_operativo"
            ],
            "listo",
        )


    def test_02_detalle_legacy_expone_next_enviado(
        self,
    ):

        pedido = self.pedido(
            estado="preparando",
        )

        response = self.client.get(
            reverse(
                "core:pedido_detalle",
                kwargs={
                    "pk":
                        pedido.pk,
                },
            )
        )

        self.assertEqual(
            response.context[
                "siguiente_estado_operativo"
            ],
            "enviado",
        )

        self.assertFalse(
            response.context[
                "es_pedido_restaurante"
            ]
        )


    def test_03_restaurante_crea_evento_usuario_sin_whatsapp(
        self,
    ):

        pedido = self.pedido(
            estado="preparando",
            tipo_orden="domicilio",
        )

        with patch(
            (
                "core.services."
                "pedido_notificaciones."
                "notificar_estado_pedido_whatsapp"
            )
        ) as notify:

            response = self.post_estado(
                pedido,
                "listo",
            )

        self.assertEqual(
            response.status_code,
            302,
        )

        pedido.refresh_from_db()

        self.assertEqual(
            pedido.estado,
            "listo",
        )

        evento = (
            PedidoEstadoEvento.objects.get(
                pedido=pedido
            )
        )

        self.assertEqual(
            evento.usuario_id,
            self.admin.id,
        )

        notify.assert_not_called()


    def test_04_legacy_conserva_notificacion(
        self,
    ):

        pedido = self.pedido(
            estado="preparando",
        )

        with patch(
            (
                "core.services."
                "pedido_notificaciones."
                "notificar_estado_pedido_whatsapp"
            ),
            return_value={
                "enviado":
                    False,
                "aplicable":
                    False,
                "motivo":
                    "Estado sin notificación TEST.",
            },
        ) as notify:

            response = self.post_estado(
                pedido,
                "enviado",
            )

        self.assertEqual(
            response.status_code,
            302,
        )

        pedido.refresh_from_db()

        self.assertEqual(
            pedido.estado,
            "enviado",
        )

        notify.assert_called_once()

        evento = (
            PedidoEstadoEvento.objects.get(
                pedido=pedido
            )
        )

        self.assertEqual(
            evento.usuario_id,
            self.admin.id,
        )


    def test_05_doble_click_no_duplica_evento(
        self,
    ):

        pedido = self.pedido(
            estado="preparando",
            tipo_orden="domicilio",
        )

        with patch(
            (
                "core.services."
                "pedido_notificaciones."
                "notificar_estado_pedido_whatsapp"
            )
        ) as notify:

            first = self.post_estado(
                pedido,
                "listo",
            )

            second = self.post_estado(
                pedido,
                "listo",
            )

        self.assertEqual(
            first.status_code,
            302,
        )

        self.assertEqual(
            second.status_code,
            302,
        )

        self.assertEqual(
            PedidoEstadoEvento.objects.filter(
                pedido=pedido
            ).count(),
            1,
        )

        notify.assert_not_called()


    def test_06_domicilio_listo_avanza_en_camino(
        self,
    ):

        pedido = self.pedido(
            estado="listo",
            tipo_orden="domicilio",
        )

        with patch(
            (
                "core.services."
                "pedido_notificaciones."
                "notificar_estado_pedido_whatsapp"
            )
        ) as notify:

            response = self.post_estado(
                pedido,
                "en_camino",
            )

        self.assertEqual(
            response.status_code,
            302,
        )

        pedido.refresh_from_db()

        self.assertEqual(
            pedido.estado,
            "en_camino",
        )

        notify.assert_not_called()


    def test_07_para_llevar_listo_entregado(
        self,
    ):

        pedido = self.pedido(
            estado="listo",
            tipo_orden="para_llevar",
        )

        with patch(
            (
                "core.services."
                "pedido_notificaciones."
                "notificar_estado_pedido_whatsapp"
            )
        ) as notify:

            response = self.post_estado(
                pedido,
                "entregado",
            )

        self.assertEqual(
            response.status_code,
            302,
        )

        pedido.refresh_from_db()

        self.assertEqual(
            pedido.estado,
            "entregado",
        )

        notify.assert_not_called()


    def test_08_cliente_cross_tenant_es_404(
        self,
    ):

        User = get_user_model()

        cliente_user = (
            User.objects.create_user(
                username=
                    "r3-panel-cliente",

                password=
                    "test-only-password",
            )
        )

        PerfilUsuario.objects.create(
            usuario=
                cliente_user,

            empresa=
                self.empresa,

            rol=
                PerfilUsuario
                .Rol
                .CLIENTE,

            activo=True,
        )

        pedido_ajeno = self.pedido(
            estado=
                "preparando",

            tipo_orden=
                "domicilio",

            empresa=
                self.otra_empresa,
        )

        self.client.force_login(
            cliente_user
        )

        # La licencia creada en setUp pertenece
        # a self.empresa, por lo que el middleware
        # debe conservar la sesión del cliente.
        session = self.client.session

        self.assertTrue(
            session.session_key
        )

        with patch(
            (
                "core.services."
                "pedido_notificaciones."
                "notificar_estado_pedido_whatsapp"
            )
        ) as notify:

            response = self.post_estado(
                pedido_ajeno,
                "listo",
                cliente=True,
            )

        self.assertEqual(
            response.status_code,
            404,
        )

        pedido_ajeno.refresh_from_db()

        self.assertEqual(
            pedido_ajeno.estado,
            "preparando",
        )

        self.assertFalse(
            PedidoEstadoEvento.objects.filter(
                pedido=pedido_ajeno
            ).exists()
        )

        notify.assert_not_called()
