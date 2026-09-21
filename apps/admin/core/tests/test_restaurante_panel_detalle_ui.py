from datetime import timedelta
from decimal import Decimal

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
    PedidoDetalle,
    PedidoEstadoEvento,
    PerfilUsuario,
)


class RestaurantePanelDetalleUITests(
    TestCase
):

    def setUp(self):

        User = get_user_model()

        self.admin = (
            User.objects.create_superuser(
                username=
                    "r3-detail-ui-admin",

                email=
                    "r3-detail-ui@example.com",

                password=
                    "test-only-password",
            )
        )

        self.cliente_user = (
            User.objects.create_user(
                username=
                    "r3-detail-ui-cliente",

                password=
                    "test-only-password",
            )
        )

        self.empresa = (
            Empresa.objects.create(
                nombre=
                    "Rest Detalle UI TEST",

                rfc=
                    "RDU010101AA1",
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
                "Licencia Detalle UI TEST",

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


    def pedido_restaurante(
        self,
        *,
        estado="preparando",
        tipo_orden="domicilio",
    ):

        self.counter += 1

        pedido = Pedido.objects.create(
            empresa=
                self.empresa,

            numero=(
                "PED-DETAIL-"
                +
                str(
                    self.counter
                ).zfill(4)
            ),

            estado=
                estado,

            tipo_orden=
                tipo_orden,

            cliente_nombre=
                "Juan Pérez",

            cliente_telefono=
                "3312345678",

            moneda=
                "MXN",

            tiempo_estimado_minutos=
                25,

            subtotal=
                Decimal(
                    "235.0000"
                ),

            subtotal_productos=
                Decimal(
                    "200.0000"
                ),

            subtotal_modificadores=
                Decimal(
                    "0.0000"
                ),

            subtotal_extras=
                Decimal(
                    "35.0000"
                ),

            costo_envio=(
                Decimal(
                    "35.0000"
                )
                if tipo_orden == "domicilio"
                else Decimal(
                    "0.0000"
                )
            ),

            descuento=
                Decimal(
                    "0.0000"
                ),

            total=(
                Decimal(
                    "270.0000"
                )
                if tipo_orden == "domicilio"
                else Decimal(
                    "235.0000"
                )
            ),

            direccion_entrega=(
                "Av. Prueba 123"
                if tipo_orden == "domicilio"
                else ""
            ),
        )

        PedidoDetalle.objects.create(
            pedido=
                pedido,

            producto=
                None,

            sku=
                "HAMB-001",

            nombre_producto=
                "Hamburguesa Especial",

            cantidad=
                Decimal(
                    "2.0000"
                ),

            precio_base=
                Decimal(
                    "100.0000"
                ),

            precio_modificadores=
                Decimal(
                    "0.0000"
                ),

            precio_extras=
                Decimal(
                    "17.5000"
                ),

            precio_unitario=
                Decimal(
                    "117.5000"
                ),

            descuento=
                Decimal(
                    "0.0000"
                ),

            importe=
                Decimal(
                    "235.0000"
                ),

            modificadores_snapshot=[
                {
                    "grupo_id":
                        1,

                    "grupo_nombre":
                        "Término",

                    "tipo":
                        "modificador",

                    "opciones": [
                        {
                            "opcion_id":
                                1,

                            "nombre":
                                "Medio",

                            "precio_adicional":
                                "0.0000",
                        },
                    ],
                },
            ],

            extras_snapshot=[
                {
                    "grupo_id":
                        2,

                    "grupo_nombre":
                        "Extras",

                    "tipo":
                        "extra",

                    "opciones": [
                        {
                            "opcion_id":
                                2,

                            "nombre":
                                "Queso extra",

                            "precio_adicional":
                                "7.5000",
                        },

                        {
                            "opcion_id":
                                3,

                            "nombre":
                                "Tocino",

                            "precio_adicional":
                                "10.0000",
                        },
                    ],
                },
            ],
        )

        return pedido


    def test_01_admin_detalle_configuracion_y_desglose(
        self,
    ):

        pedido = (
            self.pedido_restaurante()
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

        for text in (
            "A domicilio",
            "25 min",
            "Hamburguesa Especial",
            "Término",
            "Medio",
            "Queso extra",
            "Tocino",
            "Productos",
            "Modificadores",
            "Extras",
            "Envío",
            "270.00",
        ):
            self.assertContains(
                response,
                text,
            )


    def test_02_cliente_detalle_configuracion_y_desglose(
        self,
    ):

        pedido = (
            self.pedido_restaurante()
        )

        self.client.force_login(
            self.cliente_user
        )

        response = self.client.get(
            reverse(
                "core:cliente_pedido_detalle",
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

        for text in (
            "A domicilio",
            "25 min",
            "Hamburguesa Especial",
            "Medio",
            "Queso extra",
            "Tocino",
            "Productos",
            "Extras",
            "Envío",
            "Historial de estados",
        ):
            self.assertContains(
                response,
                text,
            )


    def test_03_domicilio_listo_next_en_camino(
        self,
    ):

        pedido = (
            self.pedido_restaurante(
                estado="listo",
                tipo_orden="domicilio",
            )
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

        self.assertContains(
            response,
            "Marcar en camino",
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


    def test_04_para_llevar_listo_next_entregado(
        self,
    ):

        pedido = (
            self.pedido_restaurante(
                estado="listo",
                tipo_orden=
                    "para_llevar",
            )
        )

        self.client.force_login(
            self.cliente_user
        )

        response = self.client.get(
            reverse(
                "core:cliente_pedido_detalle",
                kwargs={
                    "pk":
                        pedido.pk,
                },
            )
        )

        self.assertContains(
            response,
            "Para llevar",
        )

        self.assertContains(
            response,
            "Marcar entregado",
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


    def test_05_admin_historial_expone_operador(
        self,
    ):

        pedido = (
            self.pedido_restaurante()
        )

        PedidoEstadoEvento.objects.create(
            pedido=
                pedido,

            estado_anterior=
                "confirmado",

            estado_nuevo=
                "preparando",

            usuario=
                self.admin,
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

        self.assertContains(
            response,
            "Confirmado",
        )

        self.assertContains(
            response,
            "Preparando",
        )

        self.assertContains(
            response,
            self.admin.username,
        )


    def test_06_cliente_historial_no_expone_operador(
        self,
    ):

        pedido = (
            self.pedido_restaurante()
        )

        PedidoEstadoEvento.objects.create(
            pedido=
                pedido,

            estado_anterior=
                "confirmado",

            estado_nuevo=
                "preparando",

            usuario=
                self.admin,
        )

        self.client.force_login(
            self.cliente_user
        )

        response = self.client.get(
            reverse(
                "core:cliente_pedido_detalle",
                kwargs={
                    "pk":
                        pedido.pk,
                },
            )
        )

        self.assertContains(
            response,
            "Confirmado",
        )

        self.assertContains(
            response,
            "Preparando",
        )

        self.assertNotContains(
            response,
            self.admin.username,
        )
