import json
import tempfile
from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from core.integrations.evolution_client import (
    EvolutionClient,
    EvolutionClientError,
)
from core.models import Bot, Canal, Empresa, Licencia, Plantilla
from core.services import whatsapp_watchdog as wd


T0 = datetime(2026, 9, 22, 12, 0, tzinfo=dt_timezone.utc)
OWNER = "5210000000000@s.whatsapp.net"
TOKEN = "SECRET-TOKEN-VALUE"
QR_CODE = "2@QRDATA-NEVER-STORED"


class ClienteFalso:
    """EvolutionClient falso: nunca hay red."""

    def __init__(
        self,
        *,
        instancias=None,
        estados=None,
        fetch_error=None,
        errores_estado=(),
        connect_respuesta=None,
    ):
        self.instancias = instancias or []
        self.estados = estados or {}
        self.fetch_error = fetch_error
        self.errores_estado = set(errores_estado)
        self.connect_respuesta = connect_respuesta
        self.llamadas = []

    def fetch_instances(self):
        self.llamadas.append(("fetch",))
        if self.fetch_error:
            raise self.fetch_error
        return list(self.instancias)

    def connection_state(self, nombre):
        self.llamadas.append(("state", nombre))
        if nombre in self.errores_estado:
            raise EvolutionClientError("Evolution respondió HTTP 500.")
        return {"name": nombre, "state": self.estados.get(nombre, "desconocido")}

    def restart_instance(self, nombre):
        self.llamadas.append(("restart", nombre))
        return {"name": nombre, "state": "connecting"}

    def connect_instance(self, nombre):
        self.llamadas.append(("connect", nombre))
        if self.connect_respuesta is not None:
            return self.connect_respuesta
        return {"instance": {"instanceName": nombre, "state": "connecting"}}

    def acciones(self):
        return [c for c in self.llamadas if c[0] in ("restart", "connect")]


def instancia(nombre, *, owner=True, reason=None, stored="connecting"):
    item = {
        "name": nombre,
        "connectionStatus": stored,
        "integration": "WHATSAPP-BAILEYS",
        "token": TOKEN,
        "number": "5210000000000",
        "disconnectionReasonCode": reason,
        "disconnectionObject": '{"jid":"5210000000000@s.whatsapp.net"}',
    }
    if owner:
        item["ownerJid"] = OWNER
    return item


# TNL-WHATSAPP-WATCHDOG-V1
class WhatsappWatchdogTests(TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ruta = Path(self.tmp.name) / "estado.json"
        self.almacen = wd.EstadoWatchdogArchivo(self.ruta)

        self.empresa, self.canal = self.crear_empresa("Watchdog Uno", "WDU010101AA1")
        self.nombre = self.canal.identificador

    def crear_empresa(self, nombre, rfc, *, estado="activa", licencia=True, canal_activo=True):
        empresa = Empresa.objects.create(nombre=nombre, rfc=rfc, estado=estado)
        if licencia:
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
        bot = Bot.objects.create(empresa=empresa, plantilla=plantilla, nombre=f"Bot {nombre}", activo=True)
        canal = Canal.objects.create(
            bot=bot,
            tipo="whatsapp",
            nombre="WhatsApp",
            identificador=f"tnl-e{empresa.id}-i1",
            activo=canal_activo,
        )
        return empresa, canal

    def cliente(self, estado, **kwargs):
        owner = kwargs.pop("owner", True)
        reason = kwargs.pop("reason", None)
        extra = kwargs.pop("extra_instancias", [])
        return ClienteFalso(
            instancias=[instancia(self.nombre, owner=owner, reason=reason)] + extra,
            estados={self.nombre: estado},
            **kwargs,
        )

    def pasada(self, cliente, minuto, **kwargs):
        return wd.ejecutar_pasada(
            cliente=cliente,
            almacen=kwargs.pop("almacen", self.almacen),
            ahora=T0 + timedelta(minutes=minuto),
            **kwargs,
        )

    def resultado(self, salida):
        return salida["instancias"][0]

    def estado_guardado(self):
        return json.loads(self.ruta.read_text(encoding="utf-8"))["instancias"][self.nombre]

    # --- A-C -----------------------------------------------------------------

    def test_a_open_es_sano_sin_accion(self):
        cliente = self.cliente("open")
        salida = self.pasada(cliente, 0)
        self.assertEqual(self.resultado(salida)["clasificacion"], wd.HEALTHY)
        self.assertEqual(salida["resumen"]["healthy"], 1)
        self.assertEqual(cliente.acciones(), [])

    def test_b_primera_observacion_connecting_no_actua(self):
        cliente = self.cliente("connecting")
        salida = self.pasada(cliente, 0)
        r = self.resultado(salida)
        self.assertEqual(r["clasificacion"], wd.RECOVERABLE_CONNECTING)
        self.assertEqual(r["accion"], "observing")
        self.assertEqual(cliente.acciones(), [])

    def test_c_tres_observaciones_connecting_reinicia_una_vez(self):
        cliente = self.cliente("connecting")
        for minuto in (0, 1, 2):
            salida = self.pasada(cliente, minuto)
        self.assertEqual(self.resultado(salida)["accion"], "restart")
        self.assertEqual(cliente.acciones(), [("restart", self.nombre)])
        self.assertEqual(salida["resumen"]["recovered"], 1)

    # --- D-H -----------------------------------------------------------------

    def test_d_enfriamiento_impide_segunda_accion(self):
        cliente = self.cliente("connecting")
        for minuto in (0, 1, 2):
            self.pasada(cliente, minuto)
        for minuto in range(3, 12):
            salida = self.pasada(cliente, minuto)
            self.assertEqual(self.resultado(salida)["accion"], "cooldown")
        self.assertEqual(len(cliente.acciones()), 1)
        self.pasada(cliente, 12)
        self.assertEqual(len(cliente.acciones()), 2)

    def test_e_close_con_owner_y_motivo_seguro_conecta(self):
        cliente = self.cliente("close", reason=428)
        for minuto in (0, 1, 2):
            salida = self.pasada(cliente, minuto)
        self.assertEqual(self.resultado(salida)["clasificacion"], wd.RECOVERABLE_CLOSE)
        self.assertEqual(self.resultado(salida)["accion"], "connect")
        self.assertEqual(cliente.acciones(), [("connect", self.nombre)])

    def test_f_close_401_requiere_humano_sin_accion(self):
        cliente = self.cliente("close", reason=401)
        for minuto in range(0, 30):
            salida = self.pasada(cliente, minuto)
        self.assertEqual(self.resultado(salida)["clasificacion"], wd.REQUIRES_HUMAN)
        self.assertEqual(salida["resumen"]["human_required"], 1)
        self.assertEqual(cliente.acciones(), [])

    def test_f2_otros_motivos_invalidos_requieren_humano(self):
        for reason in (402, 403, 406):
            with self.subTest(reason=reason):
                self.assertEqual(
                    wd.clasificar_instancia(
                        estado_vivo="close",
                        metadatos={"owner_present": True, "disconnection_reason": reason},
                    ),
                    wd.REQUIRES_HUMAN,
                )

    def test_g_close_sin_owner_requiere_humano(self):
        cliente = self.cliente("close", owner=False)
        for minuto in range(0, 5):
            salida = self.pasada(cliente, minuto)
        self.assertEqual(self.resultado(salida)["clasificacion"], wd.REQUIRES_HUMAN)
        self.assertEqual(cliente.acciones(), [])

    def test_h_estado_inesperado_es_desconocido(self):
        cliente = self.cliente("refused")
        for minuto in range(0, 5):
            salida = self.pasada(cliente, minuto)
        self.assertEqual(self.resultado(salida)["clasificacion"], wd.UNKNOWN)
        self.assertEqual(salida["resumen"]["unknown"], 1)
        self.assertEqual(cliente.acciones(), [])

    def test_h2_instancia_ausente_en_evolution_es_desconocida(self):
        cliente = ClienteFalso(instancias=[], estados={self.nombre: "close"})
        salida = self.pasada(cliente, 0)
        self.assertEqual(self.resultado(salida)["clasificacion"], wd.UNKNOWN)

    # --- I -------------------------------------------------------------------

    def test_i_evolution_no_disponible_no_rompe_la_pasada(self):
        _, canal2 = self.crear_empresa("Watchdog Dos", "WDD020202BB2")
        cliente = ClienteFalso(fetch_error=EvolutionClientError("No fue posible conectar con Evolution."))
        salida = self.pasada(cliente, 0)
        self.assertEqual(salida["resumen"]["checked"], 2)
        self.assertEqual(salida["resumen"]["unknown"], 2)
        self.assertEqual(salida["resumen"]["errors"], 1)
        self.assertEqual(cliente.acciones(), [])
        # Sin Evolution no se consulta estado instancia por instancia.
        self.assertEqual([c for c in cliente.llamadas if c[0] == "state"], [])

    def test_i2_fallo_de_una_instancia_no_detiene_las_demas(self):
        _, canal2 = self.crear_empresa("Watchdog Dos", "WDD020202BB2")
        cliente = ClienteFalso(
            instancias=[instancia(self.nombre), instancia(canal2.identificador)],
            estados={canal2.identificador: "open"},
            errores_estado={self.nombre},
        )
        salida = self.pasada(cliente, 0)
        clases = {r["instancia"]: r["clasificacion"] for r in salida["instancias"]}
        self.assertEqual(clases, {self.nombre: wd.UNKNOWN, canal2.identificador: wd.HEALTHY})
        self.assertEqual(salida["resumen"]["errors"], 1)

    def test_i3_comando_imprime_resumen_y_senala_error(self):
        cliente = ClienteFalso(fetch_error=EvolutionClientError("No fue posible conectar con Evolution."))
        salida = StringIO()
        with patch("core.services.whatsapp_watchdog._crear_cliente", return_value=cliente):
            with self.assertRaises(CommandError):
                call_command("check_whatsapp_instances", "--state-file", str(self.ruta), stdout=salida)
        texto = salida.getvalue()
        self.assertIn("checked=1", texto)
        self.assertIn("unknown=1", texto)
        self.assertIn("errors=1", texto)

    # --- J-L -----------------------------------------------------------------

    def test_j_connect_con_qr_marca_humano_y_no_reintenta(self):
        cliente = self.cliente(
            "close",
            connect_respuesta={"pairingCode": None, "code": QR_CODE, "base64": "data:image/png;base64,AAAA", "count": 1},
        )
        for minuto in (0, 1, 2):
            salida = self.pasada(cliente, minuto)
        r = self.resultado(salida)
        self.assertEqual(r["accion"], "pairing_required")
        self.assertEqual(r["clasificacion"], wd.REQUIRES_HUMAN)
        # Ni pasado el enfriamiento vuelve a intentar.
        for minuto in range(3, 40):
            self.pasada(cliente, minuto)
        self.assertEqual(cliente.acciones(), [("connect", self.nombre)])
        self.assertTrue(self.estado_guardado()["requiere_humano"])
        # Al volver a open se limpia la marca.
        cliente.estados[self.nombre] = "open"
        self.pasada(cliente, 41)
        self.assertFalse(self.estado_guardado()["requiere_humano"])

    def test_k_limite_por_hora_impide_cuarto_intento(self):
        cliente = self.cliente("connecting")
        for minuto in (0, 1, 2, 12, 22):
            self.pasada(cliente, minuto)
        self.assertEqual(len(cliente.acciones()), 3)
        salida = self.pasada(cliente, 32)
        self.assertEqual(self.resultado(salida)["accion"], "hourly_limit")
        self.assertEqual(len(cliente.acciones()), 3)
        # Cuando el primer intento sale de la ventana de 1 hora, se permite otro.
        self.pasada(cliente, 62)
        self.assertEqual(len(cliente.acciones()), 4)

    def test_l_sano_reinicia_contadores_transitorios(self):
        cliente = self.cliente("connecting")
        self.pasada(cliente, 0)
        self.pasada(cliente, 1)
        self.assertEqual(self.estado_guardado()["consecutivos"], 2)
        cliente.estados[self.nombre] = "open"
        self.pasada(cliente, 2)
        self.assertEqual(self.estado_guardado()["consecutivos"], 0)
        cliente.estados[self.nombre] = "connecting"
        self.pasada(cliente, 3)
        self.pasada(cliente, 4)
        self.assertEqual(cliente.acciones(), [])
        self.pasada(cliente, 5)
        self.assertEqual(len(cliente.acciones()), 1)

    # --- M-O -----------------------------------------------------------------

    def test_m_canal_inactivo_y_huerfanas_ignorados(self):
        self.canal.activo = False
        self.canal.save(update_fields=["activo"])
        cliente = self.cliente("close", extra_instancias=[instancia("tnl-e999-i9")])
        salida = self.pasada(cliente, 0)
        self.assertEqual(salida["resumen"]["checked"], 0)
        self.assertEqual(cliente.llamadas, [])

    def test_m2_huerfana_nunca_se_consulta(self):
        cliente = self.cliente("open", extra_instancias=[instancia("tnl-e999-i9")])
        self.pasada(cliente, 0)
        consultadas = {c[1] for c in cliente.llamadas if c[0] == "state"}
        self.assertEqual(consultadas, {self.nombre})

    def test_n_empresa_suspendida_o_sin_licencia_ignorada(self):
        self.empresa.estado = "suspendida"
        self.empresa.save(update_fields=["estado"])
        crear = self.crear_empresa("Sin Licencia", "WDS030303CC3", licencia=False)
        cliente = ClienteFalso(estados={self.nombre: "close", crear[1].identificador: "close"})
        salida = self.pasada(cliente, 0)
        self.assertEqual(salida["resumen"]["checked"], 0)
        self.assertEqual(cliente.llamadas, [])

    def test_n2_identificador_no_administrado_ignorado(self):
        self.canal.identificador = "otra-instancia"
        self.canal.save(update_fields=["identificador"])
        cliente = ClienteFalso(estados={"otra-instancia": "close"})
        self.assertEqual(self.pasada(cliente, 0)["resumen"]["checked"], 0)

    def test_o_dry_run_no_actua_ni_guarda(self):
        cliente = self.cliente("connecting")
        for minuto in range(0, 10):
            salida = self.pasada(cliente, minuto, dry_run=True)
        self.assertEqual(self.resultado(salida)["clasificacion"], wd.RECOVERABLE_CONNECTING)
        self.assertEqual(cliente.acciones(), [])
        self.assertFalse(self.ruta.exists())

    def test_o2_dry_run_con_umbral_cumplido_no_actua(self):
        entrada = wd._entrada_vacia()
        entrada["consecutivos"] = 5
        almacen = wd.EstadoWatchdogMemoria({self.nombre: entrada})
        cliente = self.cliente("close")
        salida = self.pasada(cliente, 0, almacen=almacen, dry_run=True)
        self.assertEqual(self.resultado(salida)["accion"], "dry_run")
        self.assertEqual(cliente.acciones(), [])
        self.assertEqual(almacen.instancias[self.nombre]["consecutivos"], 5)

    def test_o3_comando_dry_run(self):
        cliente = self.cliente("connecting")
        salida = StringIO()
        with patch("core.services.whatsapp_watchdog._crear_cliente", return_value=cliente):
            call_command("check_whatsapp_instances", "--dry-run", "--state-file", str(self.ruta), stdout=salida)
        self.assertIn("dry_run=1", salida.getvalue())
        self.assertIn(f"instance={self.nombre}", salida.getvalue())
        self.assertEqual(cliente.acciones(), [])

    # --- P-R -----------------------------------------------------------------

    def test_p_estado_sin_datos_sensibles(self):
        cliente = self.cliente(
            "close",
            connect_respuesta={"code": QR_CODE, "base64": "data:image/png;base64,AAAA"},
        )
        for minuto in (0, 1, 2, 3):
            self.pasada(cliente, minuto)
        texto = self.ruta.read_text(encoding="utf-8")
        for secreto in ("5210000000000", TOKEN, QR_CODE, "base64", "data:image", "jid", "ownerJid"):
            self.assertNotIn(secreto, texto)
        self.assertIn(self.nombre, texto)

    def test_q_estado_corrupto_no_provoca_tormenta(self):
        self.ruta.write_text("{esto no es json", encoding="utf-8")
        cliente = self.cliente("connecting")
        salida = self.pasada(cliente, 0)
        self.assertTrue(salida["resumen"]["state_corrupt"])
        self.assertEqual(cliente.acciones(), [])
        # El archivo quedó reescrito y válido; se necesitan 3 observaciones nuevas.
        self.assertEqual(self.estado_guardado()["consecutivos"], 1)
        self.pasada(cliente, 1)
        self.assertEqual(cliente.acciones(), [])
        self.pasada(cliente, 2)
        self.assertEqual(len(cliente.acciones()), 1)

    def test_q2_estructura_invalida_se_trata_como_corrupta(self):
        for contenido in (
            json.dumps({"version": 1, "instancias": []}),
            json.dumps({"version": 1, "instancias": {"tnl-e1-i1": {"consecutivos": "muchos"}}}),
            json.dumps({"version": 99, "instancias": {}}),
        ):
            with self.subTest(contenido=contenido):
                self.ruta.write_text(contenido, encoding="utf-8")
                instancias, corrupto = self.almacen.cargar()
                self.assertTrue(corrupto)
                self.assertEqual(instancias, {})

    def test_r_si_no_se_puede_guardar_el_intento_no_se_actua(self):
        entrada = wd._entrada_vacia()
        entrada["consecutivos"] = 5

        class AlmacenSoloLectura(wd.EstadoWatchdogMemoria):
            def guardar(self, instancias):
                raise OSError("disco de solo lectura")

        almacen = AlmacenSoloLectura({self.nombre: entrada})
        cliente = self.cliente("connecting")
        salida = self.pasada(cliente, 0, almacen=almacen)
        self.assertEqual(self.resultado(salida)["accion"], "state_not_saved")
        self.assertEqual(cliente.acciones(), [])
        self.assertGreaterEqual(salida["resumen"]["errors"], 1)

    def test_r2_escritura_atomica_sin_temporales(self):
        cliente = self.cliente("open")
        self.pasada(cliente, 0)
        self.assertEqual(sorted(p.name for p in Path(self.tmp.name).iterdir()), ["estado.json"])


# TNL-WHATSAPP-WATCHDOG-V1
class EvolutionClientWatchdogTests(SimpleTestCase):

    def setUp(self):
        patcher = patch.object(EvolutionClient, "_read_api_key", return_value="test-key")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client_evo = EvolutionClient()

    def test_restart_http_200_con_error_es_fallo(self):
        with patch.object(self.client_evo, "_request", return_value={"error": True, "message": "x"}):
            with self.assertRaises(EvolutionClientError):
                self.client_evo.restart_instance("tnl-e4-i4")

    def test_restart_sin_objeto_instance_es_fallo(self):
        with patch.object(self.client_evo, "_request", return_value={}):
            with self.assertRaises(EvolutionClientError):
                self.client_evo.restart_instance("tnl-e4-i4")

    def test_restart_exitoso(self):
        with patch.object(
            self.client_evo, "_request",
            return_value={"instance": {"instanceName": "tnl-e4-i4", "status": "connecting"}},
        ) as request:
            self.assertEqual(
                self.client_evo.restart_instance("tnl-e4-i4"),
                {"name": "tnl-e4-i4", "state": "connecting"},
            )
        request.assert_called_once_with("POST", "/instance/restart/tnl-e4-i4", timeout=30)

    def test_nombre_no_administrado_no_llama_a_evolution(self):
        with patch.object(self.client_evo, "_request") as request:
            for nombre in ("", "../instance", "tnl-e4-i4/../x", "otra"):
                with self.subTest(nombre=nombre):
                    with self.assertRaises(EvolutionClientError):
                        self.client_evo.restart_instance(nombre)
                    with self.assertRaises(EvolutionClientError):
                        self.client_evo.connection_state(nombre)
        request.assert_not_called()

    def test_connection_state_normaliza(self):
        with patch.object(
            self.client_evo, "_request",
            return_value={"instance": {"instanceName": "tnl-e4-i4", "state": "OPEN"}},
        ) as request:
            self.assertEqual(self.client_evo.connection_state("tnl-e4-i4")["state"], "open")
        request.assert_called_once_with("GET", "/instance/connectionState/tnl-e4-i4", timeout=15)
        with patch.object(self.client_evo, "_request", return_value={}):
            self.assertEqual(self.client_evo.connection_state("tnl-e4-i4")["state"], "desconocido")

    def test_summary_expone_motivo_sin_datos_sensibles(self):
        resumen = EvolutionClient._summary(instancia("tnl-e4-i4", reason="401"))
        self.assertEqual(resumen["disconnection_reason"], 401)
        self.assertTrue(resumen["owner_present"])
        texto = json.dumps(resumen)
        for secreto in ("5210000000000", TOKEN, "jid"):
            self.assertNotIn(secreto, texto)
