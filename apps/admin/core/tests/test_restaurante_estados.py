from django.contrib.auth import (
    get_user_model,
)
from django.core.exceptions import (
    ValidationError,
)
from django.test import TestCase

from core.models import (
    Empresa,
    Pedido,
    PedidoEstadoEvento,
)

from core.services.pedidos import (
    cambiar_estado_pedido,
    siguiente_estado_operativo_pedido,
)


class RestauranteEstadosTests(
    TestCase
):

    def setUp(self):

        self.empresa = (
            Empresa.objects.create(
                nombre=
                    "Rest Estados TEST",

                rfc=
                    "RET010101AA1",
            )
        )

        User = get_user_model()

        self.usuario = (
            User.objects.create_user(
                username=
                    "rest-estados-test",

                password=
                    "test-no-production",
            )
        )

        self.counter = 0


    def pedido(
        self,
        *,
        estado,
        tipo_orden="",
    ):

        self.counter += 1

        return Pedido.objects.create(
            empresa=self.empresa,

            numero=(
                "PED-EST-"
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


    def test_01_legacy_confirmado_preparando_crea_evento(
        self,
    ):

        pedido = self.pedido(
            estado="confirmado"
        )

        result = cambiar_estado_pedido(
            pedido_id=
                pedido.id,

            nuevo_estado=
                "preparando",
        )

        self.assertTrue(
            result[
                "cambio_real"
            ]
        )

        pedido.refresh_from_db()

        self.assertEqual(
            pedido.estado,
            "preparando",
        )

        evento = (
            PedidoEstadoEvento.objects.get(
                pedido=pedido
            )
        )

        self.assertEqual(
            evento.estado_anterior,
            "confirmado",
        )

        self.assertEqual(
            evento.estado_nuevo,
            "preparando",
        )


    def test_02_legacy_conserva_preparando_enviado_entregado(
        self,
    ):

        pedido = self.pedido(
            estado="preparando"
        )

        cambiar_estado_pedido(
            pedido_id=
                pedido.id,

            nuevo_estado=
                "enviado",
        )

        pedido.refresh_from_db()

        self.assertEqual(
            pedido.estado,
            "enviado",
        )

        cambiar_estado_pedido(
            pedido_id=
                pedido.id,

            nuevo_estado=
                "entregado",
        )

        pedido.refresh_from_db()

        self.assertEqual(
            pedido.estado,
            "entregado",
        )

        self.assertEqual(
            PedidoEstadoEvento.objects.filter(
                pedido=pedido
            ).count(),
            2,
        )


    def test_03_domicilio_flujo_completo(
        self,
    ):

        pedido = self.pedido(
            estado="confirmado",
            tipo_orden="domicilio",
        )

        for estado in (
            "preparando",
            "listo",
            "en_camino",
            "entregado",
        ):

            result = cambiar_estado_pedido(
                pedido_id=
                    pedido.id,

                nuevo_estado=
                    estado,
            )

            self.assertTrue(
                result[
                    "cambio_real"
                ]
            )

        pedido.refresh_from_db()

        self.assertEqual(
            pedido.estado,
            "entregado",
        )

        eventos = list(
            PedidoEstadoEvento.objects
            .filter(
                pedido=pedido
            )
            .order_by(
                "id"
            )
            .values_list(
                "estado_nuevo",
                flat=True,
            )
        )

        self.assertEqual(
            eventos,
            [
                "preparando",
                "listo",
                "en_camino",
                "entregado",
            ],
        )


    def test_04_para_llevar_listo_entregado(
        self,
    ):

        pedido = self.pedido(
            estado="listo",
            tipo_orden="para_llevar",
        )

        result = cambiar_estado_pedido(
            pedido_id=
                pedido.id,

            nuevo_estado=
                "entregado",
        )

        self.assertTrue(
            result[
                "cambio_real"
            ]
        )

        pedido.refresh_from_db()

        self.assertEqual(
            pedido.estado,
            "entregado",
        )


    def test_05_comedor_listo_entregado(
        self,
    ):

        pedido = self.pedido(
            estado="listo",
            tipo_orden="comedor",
        )

        cambiar_estado_pedido(
            pedido_id=
                pedido.id,

            nuevo_estado=
                "entregado",
        )

        pedido.refresh_from_db()

        self.assertEqual(
            pedido.estado,
            "entregado",
        )


    def test_06_domicilio_no_permite_salto_preparando_en_camino(
        self,
    ):

        pedido = self.pedido(
            estado="preparando",
            tipo_orden="domicilio",
        )

        with self.assertRaises(
            ValidationError
        ):

            cambiar_estado_pedido(
                pedido_id=
                    pedido.id,

                nuevo_estado=
                    "en_camino",
            )

        pedido.refresh_from_db()

        self.assertEqual(
            pedido.estado,
            "preparando",
        )

        self.assertFalse(
            PedidoEstadoEvento.objects.filter(
                pedido=pedido
            ).exists()
        )


    def test_07_doble_click_no_duplica_evento(
        self,
    ):

        pedido = self.pedido(
            estado="preparando",
            tipo_orden="domicilio",
        )

        first = cambiar_estado_pedido(
            pedido_id=
                pedido.id,

            nuevo_estado=
                "listo",
        )

        second = cambiar_estado_pedido(
            pedido_id=
                pedido.id,

            nuevo_estado=
                "listo",
        )

        self.assertTrue(
            first[
                "cambio_real"
            ]
        )

        self.assertFalse(
            second[
                "cambio_real"
            ]
        )

        self.assertIsNone(
            second[
                "evento"
            ]
        )

        self.assertEqual(
            PedidoEstadoEvento.objects.filter(
                pedido=pedido
            ).count(),
            1,
        )


    def test_08_evento_atribuye_usuario(
        self,
    ):

        pedido = self.pedido(
            estado="confirmado",
            tipo_orden="domicilio",
        )

        result = cambiar_estado_pedido(
            pedido_id=
                pedido.id,

            nuevo_estado=
                "preparando",

            usuario_id=
                self.usuario.id,
        )

        evento = result[
            "evento"
        ]

        self.assertEqual(
            evento.usuario_id,
            self.usuario.id,
        )


    def test_09_helper_resuelve_flujos(
        self,
    ):

        self.assertEqual(
            siguiente_estado_operativo_pedido(
                "preparando"
            ),
            "enviado",
        )

        self.assertEqual(
            siguiente_estado_operativo_pedido(
                "preparando",
                tipo_orden="domicilio",
            ),
            "listo",
        )

        self.assertEqual(
            siguiente_estado_operativo_pedido(
                "listo",
                tipo_orden="domicilio",
            ),
            "en_camino",
        )

        self.assertEqual(
            siguiente_estado_operativo_pedido(
                "listo",
                tipo_orden="para_llevar",
            ),
            "entregado",
        )

        self.assertEqual(
            siguiente_estado_operativo_pedido(
                "listo",
                tipo_orden="comedor",
            ),
            "entregado",
        )


    def test_10_evento_no_marca_whatsapp_en_r3(
        self,
    ):

        pedido = self.pedido(
            estado="preparando",
            tipo_orden="domicilio",
        )

        result = cambiar_estado_pedido(
            pedido_id=
                pedido.id,

            nuevo_estado=
                "listo",
        )

        evento = result[
            "evento"
        ]

        self.assertFalse(
            evento
            .notificacion_whatsapp_enviada
        )

        self.assertIsNone(
            evento
            .notificacion_whatsapp_intentada_en
        )

        self.assertEqual(
            evento.message_id,
            "",
        )

        self.assertEqual(
            evento.notificacion_error,
            "",
        )
