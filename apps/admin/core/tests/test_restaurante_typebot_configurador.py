import json
from unittest.mock import patch

from django.http import JsonResponse
from django.test import (
    RequestFactory,
    SimpleTestCase,
)

from core.views_api import (
    restaurante_producto_configurador,
)


class RestauranteTypebotConfiguradorTests(
    SimpleTestCase
):

    def setUp(self):

        self.factory = (
            RequestFactory()
        )


    def payload_detalle(self):

        return {
            "ok": True,
            "bot_id": 77,
            "empresa": "Rest TEST",
            "producto_id": 900,
            "nombre": "Hamburguesa TEST",
            "precio": "100.00",
            "requiere_configuracion": True,
            "grupos": [
                {
                    "id": 10,
                    "nombre": "Término",
                    "tipo": "modificador",
                    "obligatorio": True,
                    "minimo": 1,
                    "maximo": 1,
                    "orden": 10,
                    "opciones": [
                        {
                            "id": 101,
                            "nombre": "Medio",
                            "precio_adicional": "0.00",
                            "orden": 10,
                        },
                        {
                            "id": 102,
                            "nombre": "Bien cocido",
                            "precio_adicional": "5.50",
                            "orden": 20,
                        },
                    ],
                },
                {
                    "id": 20,
                    "nombre": "Extras",
                    "tipo": "extra",
                    "obligatorio": False,
                    "minimo": 0,
                    "maximo": 3,
                    "orden": 20,
                    "opciones": [
                        {
                            "id": 201,
                            "nombre": "Queso",
                            "precio_adicional": "20.00",
                            "orden": 10,
                        },
                        {
                            "id": 202,
                            "nombre": "Queso",
                            "precio_adicional": "20.00",
                            "orden": 20,
                        },
                    ],
                },
            ],
        }


    def decode(
        self,
        response,
    ):

        return json.loads(
            response.content.decode(
                "utf-8"
            )
        )


    @patch(
        "core.views_api."
        "restaurante_producto_detalle"
    )
    def test_01_primer_grupo_se_aplana(
        self,
        detalle_mock,
    ):

        detalle_mock.return_value = (
            JsonResponse(
                self.payload_detalle()
            )
        )

        request = self.factory.get(
            (
                "/api/typebot/restaurante/"
                "producto/configurador/"
            ),
            {
                "bot_id": "77",
                "producto_id": "900",
                "grupo_indice": "0",
            },
        )

        response = (
            restaurante_producto_configurador(
                request
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        data = self.decode(
            response
        )

        self.assertTrue(
            data["ok"]
        )

        self.assertFalse(
            data["terminado"]
        )

        self.assertEqual(
            data["grupos_cantidad"],
            2,
        )

        self.assertEqual(
            data["grupo_id"],
            10,
        )

        self.assertEqual(
            data["grupo_nombre"],
            "Término",
        )

        self.assertTrue(
            data["grupo_obligatorio"]
        )

        self.assertEqual(
            data["grupo_minimo"],
            1,
        )

        self.assertEqual(
            data["grupo_maximo"],
            1,
        )

        self.assertEqual(
            data["opcion_ids"],
            [
                101,
                102,
            ],
        )

        self.assertEqual(
            data["opcion_etiquetas"],
            [
                "1. Medio",
                "2. Bien cocido (+5.50)",
            ],
        )

        self.assertEqual(
            data["siguiente_indice"],
            1,
        )

        detalle_mock.assert_called_once_with(
            request
        )


    @patch(
        "core.views_api."
        "restaurante_producto_detalle"
    )
    def test_02_etiquetas_duplicadas_son_unicas(
        self,
        detalle_mock,
    ):

        detalle_mock.return_value = (
            JsonResponse(
                self.payload_detalle()
            )
        )

        request = self.factory.get(
            "/adapter/",
            {
                "grupo_indice": "1",
            },
        )

        response = (
            restaurante_producto_configurador(
                request
            )
        )

        data = self.decode(
            response
        )

        self.assertEqual(
            data["grupo_id"],
            20,
        )

        self.assertFalse(
            data["grupo_obligatorio"]
        )

        self.assertEqual(
            data["grupo_maximo"],
            3,
        )

        self.assertEqual(
            data["opcion_etiquetas"],
            [
                "1. Queso (+20.00)",
                "2. Queso (+20.00)",
            ],
        )

        self.assertEqual(
            len(
                data[
                    "opcion_etiquetas"
                ]
            ),
            len(
                set(
                    data[
                        "opcion_etiquetas"
                    ]
                )
            ),
        )


    @patch(
        "core.views_api."
        "restaurante_producto_detalle"
    )
    def test_03_indice_final_termina_loop(
        self,
        detalle_mock,
    ):

        detalle_mock.return_value = (
            JsonResponse(
                self.payload_detalle()
            )
        )

        request = self.factory.get(
            "/adapter/",
            {
                "grupo_indice": "2",
            },
        )

        response = (
            restaurante_producto_configurador(
                request
            )
        )

        data = self.decode(
            response
        )

        self.assertTrue(
            data["terminado"]
        )

        self.assertEqual(
            data["grupos_restantes"],
            0,
        )

        self.assertEqual(
            data["opcion_ids"],
            [],
        )


    @patch(
        "core.views_api."
        "restaurante_producto_detalle"
    )
    def test_04_producto_sin_grupos_termina(
        self,
        detalle_mock,
    ):

        payload = self.payload_detalle()

        payload[
            "requiere_configuracion"
        ] = False

        payload[
            "grupos"
        ] = []

        detalle_mock.return_value = (
            JsonResponse(
                payload
            )
        )

        request = self.factory.get(
            "/adapter/",
            {
                "grupo_indice": "0",
            },
        )

        response = (
            restaurante_producto_configurador(
                request
            )
        )

        data = self.decode(
            response
        )

        self.assertTrue(
            data["terminado"]
        )

        self.assertEqual(
            data["grupos_cantidad"],
            0,
        )

        self.assertFalse(
            data[
                "requiere_configuracion"
            ]
        )


    @patch(
        "core.views_api."
        "restaurante_producto_detalle"
    )
    def test_05_indice_invalido_no_delega(
        self,
        detalle_mock,
    ):

        request = self.factory.get(
            "/adapter/",
            {
                "grupo_indice":
                    "-1",
            },
        )

        response = (
            restaurante_producto_configurador(
                request
            )
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        detalle_mock.assert_not_called()


    @patch(
        "core.views_api."
        "restaurante_producto_detalle"
    )
    def test_06_error_detalle_se_propaga(
        self,
        detalle_mock,
    ):

        upstream = JsonResponse(
            {
                "ok": False,
                "error":
                    "Producto no encontrado para este bot.",
            },
            status=404,
        )

        detalle_mock.return_value = (
            upstream
        )

        request = self.factory.get(
            "/adapter/",
            {
                "grupo_indice":
                    "0",
            },
        )

        response = (
            restaurante_producto_configurador(
                request
            )
        )

        self.assertIs(
            response,
            upstream,
        )

        self.assertEqual(
            response.status_code,
            404,
        )


    @patch(
        "core.views_api."
        "restaurante_producto_detalle"
    )
    def test_07_post_rechazado_sin_delegar(
        self,
        detalle_mock,
    ):

        request = self.factory.post(
            "/adapter/",
            {},
        )

        response = (
            restaurante_producto_configurador(
                request
            )
        )

        self.assertEqual(
            response.status_code,
            405,
        )

        detalle_mock.assert_not_called()
