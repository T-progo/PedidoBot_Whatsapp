from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Empresa,
    Pedido,
    PedidoEstadoEvento,
)


class RestauranteNotificacionesPanelTests(
    TestCase
):

    def setUp(self):

        User = get_user_model()

        self.admin = User.objects.create_superuser(
            username="r4-panel-admin",
            email="r4-panel@example.com",
            password="test-only-password",
        )

        self.empresa = Empresa.objects.create(
            nombre="Rest R4 Panel TEST",
            rfc="R4P010101AA1",
        )

        self.counter = 0

        self.client.force_login(
            self.admin
        )


    def pedido(
        self,
        *,
        estado,
        tipo_orden,
    ):

        self.counter += 1

        return Pedido.objects.create(
            empresa=self.empresa,
            numero=(
                "PED-R4P-"
                +
                str(self.counter).zfill(4)
            ),
            estado=estado,
            tipo_orden=tipo_orden,
            cliente_nombre="Cliente R4",
            cliente_telefono="3312345678",
            moneda="MXN",
        )


    def post_estado(
        self,
        pedido,
        nuevo_estado,
    ):

        return self.client.post(
            reverse(
                "core:pedido_estado_rapido",
                kwargs={
                    "pk": pedido.pk,
                    "nuevo_estado": nuevo_estado,
                },
            ),
            {
                "origen": "detalle",
            },
            follow=False,
        )


    @patch(
        "core.services.pedido_notificaciones."
        "notificar_evento_pedido_whatsapp"
    )
    @patch(
        "core.services.pedido_notificaciones."
        "notificar_estado_pedido_whatsapp"
    )

    def test_01_preparando_restaurante_notifica_evento_r5(
        self,
        legacy_notify,
        event_notify,
    ):
        pedido = self.pedido(
            estado="confirmado",
            tipo_orden="domicilio",
        )

        event_notify.return_value = {
            "enviado": True,
            "aplicable": True,
            "motivo": "",
            "message_id": "MSG-R5-PANEL-PREPARANDO",
            "idempotente": False,
        }

        response = self.post_estado(
            pedido,
            "preparando",
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        pedido.refresh_from_db()

        self.assertEqual(
            pedido.estado,
            "preparando",
        )

        evento = PedidoEstadoEvento.objects.get(
            pedido=pedido,
            estado_nuevo="preparando",
        )

        event_notify.assert_called_once_with(
            evento_id=evento.id
        )

        legacy_notify.assert_not_called()


    @patch(
        "core.services.pedido_notificaciones."
        "notificar_evento_pedido_whatsapp"
    )
    @patch(
        "core.services.pedido_notificaciones."
        "notificar_estado_pedido_whatsapp"
    )
    def test_02_preparando_listo_notifica_evento(
        self,
        legacy_notify,
        event_notify,
    ):

        pedido = self.pedido(
            estado="preparando",
            tipo_orden="domicilio",
        )

        event_notify.return_value = {
            "enviado": True,
            "aplicable": True,
            "motivo": "",
            "message_id": "MSG-PANEL-1",
            "idempotente": False,
        }

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

        evento = PedidoEstadoEvento.objects.get(
            pedido=pedido,
            estado_nuevo="listo",
        )

        event_notify.assert_called_once_with(
            evento_id=evento.id
        )

        legacy_notify.assert_not_called()


    @patch(
        "core.services.pedido_notificaciones."
        "notificar_evento_pedido_whatsapp"
    )
    @patch(
        "core.services.pedido_notificaciones."
        "notificar_estado_pedido_whatsapp"
    )
    def test_03_listo_en_camino_notifica_evento(
        self,
        legacy_notify,
        event_notify,
    ):

        pedido = self.pedido(
            estado="listo",
            tipo_orden="domicilio",
        )

        event_notify.return_value = {
            "enviado": True,
            "aplicable": True,
            "motivo": "",
            "message_id": "MSG-PANEL-2",
            "idempotente": False,
        }

        self.post_estado(
            pedido,
            "en_camino",
        )

        pedido.refresh_from_db()

        self.assertEqual(
            pedido.estado,
            "en_camino",
        )

        evento = PedidoEstadoEvento.objects.get(
            pedido=pedido,
            estado_nuevo="en_camino",
        )

        event_notify.assert_called_once_with(
            evento_id=evento.id
        )

        legacy_notify.assert_not_called()


    @patch(
        "core.services.pedido_notificaciones."
        "notificar_evento_pedido_whatsapp"
    )
    @patch(
        "core.services.pedido_notificaciones."
        "notificar_estado_pedido_whatsapp"
    )

    def test_04_para_llevar_listo_entregado_notifica_evento_r5(
        self,
        legacy_notify,
        event_notify,
    ):
        pedido = self.pedido(
            estado="listo",
            tipo_orden="para_llevar",
        )

        event_notify.return_value = {
            "enviado": True,
            "aplicable": True,
            "motivo": "",
            "message_id": "MSG-R5-PANEL-ENTREGADO",
            "idempotente": False,
        }

        self.post_estado(
            pedido,
            "entregado",
        )

        pedido.refresh_from_db()

        self.assertEqual(
            pedido.estado,
            "entregado",
        )

        evento = PedidoEstadoEvento.objects.get(
            pedido=pedido,
            estado_nuevo="entregado",
        )

        event_notify.assert_called_once_with(
            evento_id=evento.id
        )

        legacy_notify.assert_not_called()


    @patch(
        "core.services.pedido_notificaciones."
        "notificar_evento_pedido_whatsapp"
    )
    def test_05_fallo_whatsapp_no_revierte_estado(
        self,
        event_notify,
    ):

        pedido = self.pedido(
            estado="preparando",
            tipo_orden="para_llevar",
        )

        event_notify.return_value = {
            "enviado": False,
            "aplicable": True,
            "motivo":
                "Evolution no pudo enviar la notificación WhatsApp.",
            "message_id": "",
            "idempotente": False,
        }

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

        self.assertTrue(
            PedidoEstadoEvento.objects.filter(
                pedido=pedido,
                estado_nuevo="listo",
            ).exists()
        )

        event_notify.assert_called_once()


    @patch(
        "core.services.pedido_notificaciones."
        "notificar_evento_pedido_whatsapp"
    )
    def test_06_doble_click_no_segundo_intento(
        self,
        event_notify,
    ):

        pedido = self.pedido(
            estado="preparando",
            tipo_orden="domicilio",
        )

        event_notify.return_value = {
            "enviado": True,
            "aplicable": True,
            "motivo": "",
            "message_id": "MSG-ONCE",
            "idempotente": False,
        }

        self.post_estado(
            pedido,
            "listo",
        )

        self.post_estado(
            pedido,
            "listo",
        )

        pedido.refresh_from_db()

        self.assertEqual(
            pedido.estado,
            "listo",
        )

        self.assertEqual(
            PedidoEstadoEvento.objects.filter(
                pedido=pedido,
                estado_nuevo="listo",
            ).count(),
            1,
        )

        event_notify.assert_called_once()


    @patch(
        "core.services.pedido_notificaciones."
        "notificar_evento_pedido_whatsapp"
    )
    @patch(
        "core.services.pedido_notificaciones."
        "notificar_estado_pedido_whatsapp"
    )
    def test_07_legacy_sigue_notificador_historico(
        self,
        legacy_notify,
        event_notify,
    ):

        pedido = self.pedido(
            estado="preparando",
            tipo_orden="",
        )

        legacy_notify.return_value = {
            "enviado": True,
            "aplicable": True,
            "motivo": "",
            "message_id": "MSG-LEGACY-PANEL",
        }

        self.post_estado(
            pedido,
            "enviado",
        )

        pedido.refresh_from_db()

        self.assertEqual(
            pedido.estado,
            "enviado",
        )

        legacy_notify.assert_called_once()
        event_notify.assert_not_called()
