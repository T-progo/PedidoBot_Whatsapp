import json
import os
import tempfile
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.integrations.evolution_client import (
    EvolutionClient,
    EvolutionClientError,
)
from core.models import (
    Bot,
    Canal,
    Empresa,
    InstalacionPlantilla,
    Licencia,
    PerfilUsuario,
    Plantilla,
    PlantillaMaestra,
)
from core.services import whatsapp_watchdog as wd
from core.tests.test_whatsapp_watchdog import (
    OWNER,
    QR_CODE,
    TOKEN,
    ClienteFalso,
    instancia,
)


MSG_CONECTADO = "WhatsApp ya está conectado."
MSG_SOLICITADA = "Se solicitó la reconexión de WhatsApp."
MSG_QR = "La sesión necesita volver a vincularse mediante QR."
MSG_ENFRIAMIENTO = "Ya se solicitó una reconexión recientemente."
MSG_EN_CURSO = "Hay una revisión de WhatsApp en curso."
MSG_NO_DISPONIBLE = "No fue posible consultar WhatsApp en este momento."


class EvolutionFalsa(ClienteFalso):
    """Reemplazo de EvolutionClient para la vista de estado."""

    def find_instance(self, nombre):
        self.llamadas.append(("find", nombre))
        for item in self.instancias:
            resumen = EvolutionClient._summary(item)
            if resumen and resumen["name"] == nombre:
                return resumen
        return None


# TNL-WHATSAPP-MANUAL-RECONNECT-V1
class ReconectarWhatsappTests(TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ruta = Path(tmp.name) / "estado.json"

        entorno = patch.dict(os.environ, {wd.ENV_RUTA_ESTADO: str(self.ruta)})
        entorno.start()
        self.addCleanup(entorno.stop)

        self.empresa, self.bot, self.canal = self.crear_cliente("Alitas Prueba", "APR010101AA1")
        self.nombre = self.canal.identificador

        self.evolution = EvolutionFalsa(
            instancias=[instancia(self.nombre)],
            estados={self.nombre: "open"},
        )
        fabrica = patch(
            "core.services.whatsapp_watchdog._crear_cliente",
            side_effect=lambda: self.evolution,
        )
        fabrica.start()
        self.addCleanup(fabrica.stop)

        # El panel exige la URL de OAuth de Google, configurada en producción.
        oauth = patch(
            "core.services.google_calendar_oauth.obtener_redirect_uri",
            return_value="https://admin.example.test/google/callback/",
        )
        oauth.start()
        self.addCleanup(oauth.stop)

        self.admin =self.crear_usuario("admin-wa", PerfilUsuario.Rol.ADMINISTRADOR)
        self.client.force_login(self.admin)

    # --- utilidades ----------------------------------------------------------

    def crear_cliente(self, nombre, rfc):
        empresa = Empresa.objects.create(nombre=nombre, rfc=rfc)
        hoy = timezone.localdate()
        Licencia.objects.create(
            empresa=empresa,
            nombre=f"Licencia {nombre}",
            estado="activa",
            fecha_inicio=hoy - timedelta(days=1),
            fecha_fin=hoy + timedelta(days=30),
        )
        plantilla = Plantilla.objects.create(
            empresa=empresa, nombre=f"Plantilla {nombre}", tipo="restaurante", activa=True
        )
        maestra = PlantillaMaestra.objects.create(
            nombre=f"Maestra {nombre}", slug=f"maestra-{rfc.lower()}", tipo="restaurante"
        )
        instalacion = InstalacionPlantilla.objects.create(
            empresa=empresa, plantilla_maestra=maestra, plantilla=plantilla, estado="lista"
        )
        bot = Bot.objects.create(empresa=empresa, plantilla=plantilla, nombre=f"Bot {nombre}", activo=True)
        canal = Canal.objects.create(
            bot=bot,
            tipo="whatsapp",
            nombre="WhatsApp",
            identificador=f"tnl-e{empresa.id}-i{instalacion.id}",
            activo=True,
        )
        return empresa, bot, canal

    def crear_usuario(self, username, rol, empresa=None):
        usuario = get_user_model().objects.create_user(username=username, password="clave-prueba")
        PerfilUsuario.objects.create(usuario=usuario, rol=rol, empresa=empresa)
        return usuario

    def url(self, empresa=None, canal=None):
        return reverse(
            "core:empresa_whatsapp_reconectar",
            args=[(empresa or self.empresa).pk, (canal or self.canal).pk],
        )

    def reconectar(self, cliente=None, data=None, **kwargs):
        return (cliente or self.client).post(self.url(**kwargs), data or {}, follow=True)

    def mensajes(self, respuesta):
        return [str(m) for m in respuesta.context["messages"]] if respuesta.context else []

    def escrituras(self):
        return self.evolution.acciones()

    def estado_guardado(self):
        return json.loads(self.ruta.read_text(encoding="utf-8"))["instancias"][self.nombre]

    def sembrar_estado(self, **campos):
        entrada = wd._entrada_vacia()
        entrada.update(campos)
        wd.EstadoWatchdogArchivo(self.ruta).guardar({self.nombre: entrada})

    def configurar(self, estado, **kwargs):
        self.evolution.instancias = [
            instancia(self.nombre, owner=kwargs.pop("owner", True), reason=kwargs.pop("reason", None))
        ]
        self.evolution.estados = {self.nombre: estado}
        self.evolution.fetch_error = None
        self.evolution.errores_estado = set()
        self.evolution.connect_respuesta = None
        for clave, valor in kwargs.items():
            setattr(self.evolution, clave, valor)

    # --- A-E: permisos y origen de la instancia ------------------------------

    def test_a_usuario_sin_permiso_no_reconecta(self):
        self.configurar("connecting")

        respuesta = Client().post(self.url())
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta["Location"].startswith("/login/"))

        for rol in (PerfilUsuario.Rol.CLIENTE, PerfilUsuario.Rol.OPERADOR):
            usuario = self.crear_usuario(f"user-{rol}", rol, empresa=self.empresa)
            otro = Client()
            otro.force_login(usuario)
            self.assertEqual(otro.post(self.url()).status_code, 403)

        self.assertEqual(self.evolution.llamadas, [])

    def test_b_canal_de_otra_empresa_no_se_puede_usar(self):
        self.configurar("connecting")
        empresa2, _, canal2 = self.crear_cliente("Otra Empresa", "OTR020202BB2")
        self.assertEqual(self.client.post(self.url(canal=canal2)).status_code, 404)
        self.assertEqual(self.client.post(self.url(empresa=empresa2)).status_code, 404)
        self.assertEqual(self.evolution.llamadas, [])

    def test_c_canal_que_no_es_whatsapp_rechazado(self):
        self.configurar("connecting")
        telegram = Canal.objects.create(
            bot=self.bot, tipo="telegram", nombre="Telegram", identificador=self.nombre, activo=True
        )
        self.assertEqual(self.client.post(self.url(canal=telegram)).status_code, 404)
        self.assertEqual(self.evolution.llamadas, [])

    def test_d_canal_inexistente_rechazado(self):
        respuesta = self.client.post(
            reverse("core:empresa_whatsapp_reconectar", args=[self.empresa.pk, 999999])
        )
        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(self.evolution.llamadas, [])

    def test_e_instancia_sale_del_canal_no_del_navegador(self):
        self.configurar("connecting")
        ajena = "tnl-e999-i9"
        self.reconectar(data={"instance": ajena, "instancia": ajena, "identificador": ajena, "nombre": ajena})
        self.assertEqual(self.escrituras(), [("restart", self.nombre)])
        self.assertNotIn(ajena, json.dumps(self.evolution.llamadas))

    # --- F-K: decisión según el estado VIVO ----------------------------------

    def test_f_conectado_no_escribe_en_evolution(self):
        respuesta = self.reconectar()
        self.assertEqual(self.mensajes(respuesta), [MSG_CONECTADO])
        self.assertEqual(self.escrituras(), [])
        self.assertEqual({c[0] for c in self.evolution.llamadas}, {"fetch", "state"})
        self.assertFalse(self.ruta.exists())
        self.assertRedirects(
            respuesta, reverse("core:empresa_detalle", args=[self.empresa.pk]) + "#whatsapp",
            fetch_redirect_response=False,
        )

    def test_g_connecting_reinicia_una_vez(self):
        self.configurar("connecting")
        respuesta = self.reconectar()
        self.assertEqual(self.escrituras(), [("restart", self.nombre)])
        self.assertEqual(self.mensajes(respuesta), [MSG_SOLICITADA])

    def test_h_close_reconecta_una_vez(self):
        self.configurar("close", reason=428)
        respuesta = self.reconectar()
        self.assertEqual(self.escrituras(), [("connect", self.nombre)])
        self.assertEqual(self.mensajes(respuesta), [MSG_SOLICITADA])

    def test_i_requiere_vinculacion_no_actua(self):
        for configuracion in ({"reason": 401}, {"owner": False}):
            with self.subTest(**configuracion):
                self.configurar("close", **configuracion)
                self.assertEqual(self.mensajes(self.reconectar()), [MSG_QR])
        # Vinculación pendiente ya marcada por el watchdog.
        self.sembrar_estado(requiere_humano=True)
        self.configurar("connecting")
        self.assertEqual(self.mensajes(self.reconectar()), [MSG_QR])
        self.assertEqual(self.escrituras(), [])

    def test_j_estado_desconocido_o_error_no_actua(self):
        casos = (
            {"estado": "refused"},
            {"estado": "connecting", "fetch_error": EvolutionClientError("Evolution respondió HTTP 500.")},
            {"estado": "connecting", "errores_estado": {self.nombre}},
        )
        for caso in casos:
            with self.subTest(**{k: str(v) for k, v in caso.items()}):
                self.configurar(
                    caso["estado"],
                    fetch_error=caso.get("fetch_error"),
                    errores_estado=caso.get("errores_estado", set()),
                )
                respuesta = self.reconectar()
                self.assertEqual(self.mensajes(respuesta), [MSG_NO_DISPONIBLE])
                self.assertNotIn("HTTP 500", respuesta.content.decode())
        self.assertEqual(self.escrituras(), [])
        self.assertEqual({c[0] for c in self.evolution.llamadas} - {"fetch", "state"}, set())

    def test_k_connect_con_qr_pide_vinculacion_sin_exponerlo(self):
        self.configurar(
            "close",
            connect_respuesta={"code": QR_CODE, "base64": "data:image/png;base64,AAAA", "count": 1},
        )
        respuesta = self.reconectar()
        self.assertEqual(self.mensajes(respuesta), [MSG_QR])
        self.assertEqual(self.escrituras(), [("connect", self.nombre)])
        html = respuesta.content.decode()
        for secreto in (QR_CODE, "data:image/png;base64,AAAA"):
            self.assertNotIn(secreto, html)
        self.assertTrue(self.estado_guardado()["requiere_humano"])
        texto = self.ruta.read_text(encoding="utf-8")
        for secreto in (QR_CODE, "base64", OWNER, TOKEN):
            self.assertNotIn(secreto, texto)
        # Un segundo clic, pasado el enfriamiento, no vuelve a pedir QR.
        self.sembrar_estado(
            requiere_humano=True,
            ultimo_intento=wd._iso(datetime.now(dt_timezone.utc) - timedelta(minutes=5)),
        )
        self.assertEqual(self.mensajes(self.reconectar()), [MSG_QR])
        self.assertEqual(len(self.escrituras()), 1)

    # --- L-N: enfriamiento y estado compartido --------------------------------

    def test_l_doble_clic_no_repite_la_accion(self):
        self.configurar("connecting")
        primera = self.reconectar()
        segunda = self.reconectar()
        self.assertEqual(self.escrituras(), [("restart", self.nombre)])
        self.assertEqual(self.mensajes(primera), [MSG_SOLICITADA])
        self.assertTrue(self.mensajes(segunda)[0].startswith(MSG_ENFRIAMIENTO))

    def test_l2_otra_reconexion_en_curso(self):
        self.configurar("connecting")
        liberar = wd.EstadoWatchdogArchivo(self.ruta).bloquear(espera=0)
        try:
            with patch.object(wd, "ESPERA_CANDADO_MANUAL", 0):
                respuesta = self.reconectar()
        finally:
            liberar()
        self.assertTrue(self.mensajes(respuesta)[0].startswith(MSG_EN_CURSO))
        self.assertEqual(self.evolution.llamadas, [])

    def test_m_respeta_una_accion_automatica_reciente(self):
        self.configurar("connecting")
        ahora = datetime.now(dt_timezone.utc)
        hace_30s = wd._iso(ahora - timedelta(seconds=30))
        self.sembrar_estado(consecutivos=4, ultimo_intento=hace_30s, intentos=[hace_30s])
        self.assertTrue(self.mensajes(self.reconectar())[0].startswith(MSG_ENFRIAMIENTO))
        self.assertEqual(self.escrituras(), [])

        # Una acción automática de hace 5 minutos no bloquea al panel
        # (el enfriamiento de 10 minutos es sólo para el timer).
        hace_5min = wd._iso(ahora - timedelta(minutes=5))
        self.sembrar_estado(consecutivos=4, ultimo_intento=hace_5min, intentos=[hace_5min])
        self.assertEqual(self.mensajes(self.reconectar()), [MSG_SOLICITADA])
        self.assertEqual(self.escrituras(), [("restart", self.nombre)])

    def test_n_intento_manual_queda_en_el_estado_compartido(self):
        self.configurar("connecting")
        antes = datetime.now(dt_timezone.utc)
        self.reconectar()
        entrada = self.estado_guardado()
        ultimo = datetime.fromisoformat(entrada["ultimo_intento"])
        self.assertTrue(antes - timedelta(seconds=1) <= ultimo <= datetime.now(dt_timezone.utc))
        self.assertEqual(entrada["intentos"], [entrada["ultimo_intento"]])
        self.assertEqual(entrada["consecutivos"], 0)
        self.assertFalse(entrada["requiere_humano"])

        # El timer ve el intento manual y respeta su enfriamiento de 10 min.
        almacen = wd.EstadoWatchdogArchivo(self.ruta)
        for minuto in (1, 2, 3):
            salida = wd.ejecutar_pasada(cliente=self.evolution, almacen=almacen, ahora=ultimo + timedelta(minutes=minuto))
        self.assertEqual(salida["instancias"][0]["accion"], "cooldown")
        self.assertEqual(self.escrituras(), [("restart", self.nombre)])

    # --- O-P: método y CSRF ----------------------------------------------------

    def test_o_solo_post(self):
        self.configurar("connecting")
        self.assertEqual(self.client.get(self.url()).status_code, 405)
        self.assertEqual(self.evolution.llamadas, [])

    def test_p_csrf_obligatorio(self):
        self.configurar("connecting")
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.admin)
        self.assertEqual(csrf.post(self.url()).status_code, 403)
        self.assertEqual(self.evolution.llamadas, [])

        csrf.get(reverse("core:empresa_detalle", args=[self.empresa.pk]))
        token = csrf.cookies["csrftoken"].value
        respuesta = csrf.post(self.url(), {"csrfmiddlewaretoken": token})
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(self.escrituras(), [("restart", self.nombre)])

    # --- Q-R: plantilla --------------------------------------------------------

    def detalle(self):
        respuesta = self.client.get(reverse("core:empresa_detalle", args=[self.empresa.pk]))
        self.assertEqual(respuesta.status_code, 200)
        return respuesta.content.decode()

    def test_q_boton_para_canal_whatsapp_activo_configurado(self):
        html = self.detalle()
        accion = self.url()
        self.assertIn(f'action="{accion}"', html)
        self.assertIn("Reconectar WhatsApp", html)
        formulario = html.split(f'action="{accion}"', 1)[1].split("</form>", 1)[0]
        # El único campo es el token CSRF: ningún nombre de instancia viaja en el form.
        self.assertEqual(formulario.count("<input"), 1)
        self.assertIn('name="csrfmiddlewaretoken"', formulario)
        self.assertEqual(self.evolution.llamadas, [])

    def test_r_sin_boton_para_otros_canales(self):
        telegram = Canal.objects.create(bot=self.bot, tipo="telegram", nombre="Telegram", activo=True)
        html = self.detalle()
        self.assertNotIn(self.url(canal=telegram), html)

        # WhatsApp pendiente o sin instancia: se muestra "Conectar", no "Reconectar".
        for cambios in ({"activo": False}, {"identificador": ""}):
            with self.subTest(**cambios):
                Canal.objects.filter(pk=self.canal.pk).update(**{"activo": True, "identificador": self.nombre, **cambios})
                self.assertNotIn(self.url(), self.detalle())

    # --- Estado VIVO en la tarjeta ------------------------------------------------

    def estado(self, vivo=True):
        url = reverse("core:empresa_whatsapp_estado", args=[self.empresa.pk, self.canal.pk])
        with patch("core.integrations.evolution_client.EvolutionClient", return_value=self.evolution):
            respuesta = self.client.get(url + ("?vivo=1" if vivo else ""))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn(OWNER, respuesta.content.decode())
        self.assertNotIn(TOKEN, respuesta.content.decode())
        return respuesta.json()

    def test_estado_vivo_en_palabras_simples(self):
        casos = (
            ("open", {}, "conectado", "Conectado"),
            ("connecting", {}, "conectando", "Conectando"),
            ("close", {"reason": 428}, "desconectado", "Desconectado"),
            ("close", {"reason": 401}, "requiere_vinculacion", "Requiere vinculación"),
            ("refused", {}, "no_disponible", "Estado no disponible"),
        )
        for estado, extra, codigo, texto in casos:
            with self.subTest(estado=estado, **extra):
                self.configurar(estado, **extra)
                self.assertEqual(self.estado()["estado_panel"], {"codigo": codigo, "texto": texto})

        self.configurar("close", errores_estado={self.nombre})
        self.assertEqual(self.estado()["estado_panel"]["codigo"], "no_disponible")

        self.sembrar_estado(requiere_humano=True)
        self.configurar("close", reason=428)
        self.assertEqual(self.estado()["estado_panel"]["codigo"], "requiere_vinculacion")
        self.assertEqual(self.escrituras(), [])

    def test_estado_sin_vivo_queda_igual(self):
        self.configurar("connecting")
        datos = self.estado(vivo=False)
        self.assertNotIn("estado_panel", datos)
        self.assertEqual(datos["state"], "connecting")
        self.assertNotIn("state", {c[0] for c in self.evolution.llamadas})
