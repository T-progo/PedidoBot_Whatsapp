from unittest.mock import patch

from django.test import TestCase

from core.integrations.evolution_client import (
    EvolutionClientError,
)

from core.models import (
    Bot,
    Canal,
    Empresa,
    Pedido,
    PedidoEstadoEvento,
)

from core.services.pedido_notificaciones import (
    construir_mensaje_estado_pedido,
    notificar_estado_pedido_whatsapp,
    notificar_evento_pedido_whatsapp,
)


class RestauranteNotificacionesTests(
    TestCase
):

    def setUp(self):

        self.empresa = Empresa.objects.create(
            nombre="Rest WhatsApp TEST",
            rfc="RWA010101AA1",
        )

        self.bot = Bot.objects.create(
            empresa=self.empresa,
            nombre="Bot Rest WhatsApp TEST",
            activo=True,
        )

        self.canal = Canal.objects.create(
            bot=self.bot,
            tipo="whatsapp",
            nombre="WhatsApp TEST",
            identificador="tnl-e999-i999",
            activo=True,
        )

        self.counter = 0


    def pedido(
        self,
        *,
        estado,
        tipo_orden,
        canal=True,
    ):

        self.counter += 1

        return Pedido.objects.create(
            empresa=self.empresa,
            canal=(
                self.canal
                if canal
                else None
            ),
            numero=(
                "PED-R4-"
                +
                str(self.counter).zfill(4)
            ),
            estado=estado,
            tipo_orden=tipo_orden,
            cliente_nombre="Cliente R4",
            cliente_telefono="3312345678",
            moneda="MXN",
        )


    def evento(
        self,
        *,
        pedido,
        anterior,
        nuevo,
    ):

        return PedidoEstadoEvento.objects.create(
            pedido=pedido,
            estado_anterior=anterior,
            estado_nuevo=nuevo,
        )


    def test_01_listo_para_llevar(self):

        msg = construir_mensaje_estado_pedido(
            numero="PED-TEST",
            estado="listo",
            tipo_orden="para_llevar",
        )

        self.assertIn(
            "recogerlo",
            msg,
        )


    def test_02_listo_domicilio(self):

        msg = construir_mensaje_estado_pedido(
            numero="PED-TEST",
            estado="listo",
            tipo_orden="domicilio",
        )

        self.assertIn(
            "domicilio",
            msg,
        )


    def test_03_en_camino_solo_domicilio(self):

        domicilio = (
            construir_mensaje_estado_pedido(
                numero="PED-TEST",
                estado="en_camino",
                tipo_orden="domicilio",
            )
        )

        recoger = (
            construir_mensaje_estado_pedido(
                numero="PED-TEST",
                estado="en_camino",
                tipo_orden="para_llevar",
            )
        )

        self.assertIn(
            "va en camino",
            domicilio,
        )

        self.assertEqual(
            recoger,
            "",
        )


    @patch(
        "core.services.pedido_notificaciones.EvolutionClient"
    )
    def test_04_evento_exitoso_persiste_message_id(
        self,
        client_class,
    ):

        pedido = self.pedido(
            estado="listo",
            tipo_orden="para_llevar",
        )

        evento = self.evento(
            pedido=pedido,
            anterior="preparando",
            nuevo="listo",
        )

        client = client_class.return_value

        client.find_instance.return_value = {
            "state": "open",
        }

        client.send_text.return_value = {
            "key": {
                "id": "MSG-R4-001",
            },
        }

        result = (
            notificar_evento_pedido_whatsapp(
                evento_id=evento.id
            )
        )

        self.assertTrue(
            result["enviado"]
        )

        self.assertFalse(
            result["idempotente"]
        )

        evento.refresh_from_db()

        self.assertTrue(
            evento.notificacion_whatsapp_enviada
        )

        self.assertIsNotNone(
            evento.notificacion_whatsapp_intentada_en
        )

        self.assertEqual(
            evento.message_id,
            "MSG-R4-001",
        )

        self.assertEqual(
            evento.notificacion_error,
            "",
        )

        client.send_text.assert_called_once()


    @patch(
        "core.services.pedido_notificaciones.EvolutionClient"
    )
    def test_05_segundo_intento_no_reenvia(
        self,
        client_class,
    ):

        pedido = self.pedido(
            estado="listo",
            tipo_orden="para_llevar",
        )

        evento = self.evento(
            pedido=pedido,
            anterior="preparando",
            nuevo="listo",
        )

        client = client_class.return_value

        client.find_instance.return_value = {
            "state": "open",
        }

        client.send_text.return_value = {
            "key": {
                "id": "MSG-R4-IDEMP",
            },
        }

        first = (
            notificar_evento_pedido_whatsapp(
                evento_id=evento.id
            )
        )

        second = (
            notificar_evento_pedido_whatsapp(
                evento_id=evento.id
            )
        )

        self.assertTrue(
            first["enviado"]
        )

        self.assertTrue(
            second["enviado"]
        )

        self.assertTrue(
            second["idempotente"]
        )

        client.send_text.assert_called_once()


    @patch(
        "core.services.pedido_notificaciones.EvolutionClient"
    )
    def test_06_fallo_evolution_no_reintenta(
        self,
        client_class,
    ):

        pedido = self.pedido(
            estado="listo",
            tipo_orden="para_llevar",
        )

        evento = self.evento(
            pedido=pedido,
            anterior="preparando",
            nuevo="listo",
        )

        client = client_class.return_value

        client.find_instance.return_value = {
            "state": "open",
        }

        client.send_text.side_effect = (
            EvolutionClientError(
                "Fallo TEST"
            )
        )

        first = (
            notificar_evento_pedido_whatsapp(
                evento_id=evento.id
            )
        )

        second = (
            notificar_evento_pedido_whatsapp(
                evento_id=evento.id
            )
        )

        self.assertFalse(
            first["enviado"]
        )

        self.assertFalse(
            second["enviado"]
        )

        self.assertTrue(
            second["idempotente"]
        )

        evento.refresh_from_db()

        self.assertFalse(
            evento.notificacion_whatsapp_enviada
        )

        self.assertIsNotNone(
            evento.notificacion_whatsapp_intentada_en
        )

        self.assertTrue(
            evento.notificacion_error
        )

        client.send_text.assert_called_once()


    @patch(
        "core.services.pedido_notificaciones.EvolutionClient"
    )
    def test_07_canal_null_compatible_postgresql(
        self,
        client_class,
    ):

        pedido = self.pedido(
            estado="listo",
            tipo_orden="para_llevar",
            canal=False,
        )

        evento = self.evento(
            pedido=pedido,
            anterior="preparando",
            nuevo="listo",
        )

        result = (
            notificar_evento_pedido_whatsapp(
                evento_id=evento.id
            )
        )

        self.assertFalse(
            result["enviado"]
        )

        evento.refresh_from_db()

        self.assertIsNotNone(
            evento.notificacion_whatsapp_intentada_en
        )

        self.assertTrue(
            evento.notificacion_error
        )

        client_class.assert_not_called()


    @patch(
        "core.services.pedido_notificaciones.EvolutionClient"
    )

    def test_08_preparando_y_entregado_aplican_evento_r5(
        self,
        client_class,
    ):
        client = client_class.return_value

        client.find_instance.return_value = {
            "state": "open",
        }

        client.send_text.side_effect = [
            {
                "key": {
                    "id": "MSG-R5-PREPARANDO",
                },
            },
            {
                "key": {
                    "id": "MSG-R5-ENTREGADO",
                },
            },
        ]

        casos = (
            (
                "confirmado",
                "preparando",
                "domicilio",
                "MSG-R5-PREPARANDO",
            ),
            (
                "en_camino",
                "entregado",
                "domicilio",
                "MSG-R5-ENTREGADO",
            ),
        )

        for (
            anterior,
            nuevo,
            tipo_orden,
            expected_message_id,
        ) in casos:

            with self.subTest(
                estado=nuevo
            ):
                pedido = self.pedido(
                    estado=nuevo,
                    tipo_orden=tipo_orden,
                )

                evento = self.evento(
                    pedido=pedido,
                    anterior=anterior,
                    nuevo=nuevo,
                )

                result = (
                    notificar_evento_pedido_whatsapp(
                        evento_id=evento.id
                    )
                )

                self.assertTrue(
                    result["aplicable"]
                )

                self.assertTrue(
                    result["enviado"]
                )

                self.assertFalse(
                    result["idempotente"]
                )

                self.assertEqual(
                    result["message_id"],
                    expected_message_id,
                )

                evento.refresh_from_db()

                self.assertIsNotNone(
                    evento
                    .notificacion_whatsapp_intentada_en
                )

                self.assertTrue(
                    evento
                    .notificacion_whatsapp_enviada
                )

                self.assertEqual(
                    evento.message_id,
                    expected_message_id,
                )

                self.assertEqual(
                    evento.notificacion_error,
                    "",
                )

        self.assertEqual(
            client.send_text.call_count,
            2,
        )


    @patch(
        "core.services.pedido_notificaciones.EvolutionClient"
    )
    def test_09_legacy_preparando_preservado(
        self,
        client_class,
    ):

        pedido = self.pedido(
            estado="preparando",
            tipo_orden="",
        )

        client = client_class.return_value

        client.find_instance.return_value = {
            "state": "open",
        }

        client.send_text.return_value = {
            "key": {
                "id": "MSG-LEGACY",
            },
        }

        result = (
            notificar_estado_pedido_whatsapp(
                pedido=pedido
            )
        )

        self.assertTrue(
            result["enviado"]
        )

        self.assertEqual(
            result["message_id"],
            "MSG-LEGACY",
        )

        client.send_text.assert_called_once()


    def test_10_evento_no_depende_wrapper_legacy(
        self,
    ):

        pedido = self.pedido(
            estado="listo",
            tipo_orden="para_llevar",
        )

        evento = self.evento(
            pedido=pedido,
            anterior="preparando",
            nuevo="listo",
        )

        # Este mock reproduce exactamente la situación
        # de los tests históricos R3.
        #
        # Si el evento dependiera del wrapper legacy,
        # recibiría {} y rompería el contrato R4.
        with patch(
            "core.services.pedido_notificaciones."
            "notificar_estado_pedido_whatsapp",
            return_value={},
        ) as legacy_mock:

            with patch(
                "core.services.pedido_notificaciones."
                "EvolutionClient"
            ) as client_class:

                client = (
                    client_class.return_value
                )

                client.find_instance.return_value = {
                    "state": "open",
                }

                client.send_text.return_value = {
                    "key": {
                        "id":
                            "MSG-R4-DESACOPLE",
                    },
                }

                result = (
                    notificar_evento_pedido_whatsapp(
                        evento_id=
                            evento.id
                    )
                )

        self.assertTrue(
            result[
                "enviado"
            ]
        )

        self.assertEqual(
            result[
                "message_id"
            ],
            "MSG-R4-DESACOPLE",
        )

        legacy_mock.assert_not_called()

        client.send_text.assert_called_once()

        evento.refresh_from_db()

        self.assertTrue(
            evento
            .notificacion_whatsapp_enviada
        )

        self.assertEqual(
            evento.message_id,
            "MSG-R4-DESACOPLE",
        )
