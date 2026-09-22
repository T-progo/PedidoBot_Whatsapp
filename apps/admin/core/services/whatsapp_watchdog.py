"""
Watchdog de instancias WhatsApp (Evolution API).

TNL-WHATSAPP-WATCHDOG-V1

Una ejecución = una pasada: revisa los canales WhatsApp activos de
empresas operativas, clasifica su estado VIVO y, sólo cuando es seguro,
pide a Evolution que recupere la conexión.

Nunca hace logout, delete ni reinicio del contenedor, y nunca guarda ni
registra QR, números, tokens ni datos de clientes.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time

from datetime import (
    datetime,
    timedelta,
    timezone as dt_timezone,
)
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows: solo desarrollo local
    fcntl = None
    import msvcrt

from core.integrations.evolution_client import (
    EvolutionClient,
)


HEALTHY = "healthy"
RECOVERABLE_CONNECTING = "recoverable_connecting"
RECOVERABLE_CLOSE = "recoverable_close"
REQUIRES_HUMAN = "requires_human"
UNKNOWN = "unknown"

RECUPERABLES = (
    RECOVERABLE_CONNECTING,
    RECOVERABLE_CLOSE,
)

# Baileys no reconecta estos cierres: la sesión ya no es válida
# y se necesita vincular de nuevo (QR).
MOTIVOS_SESION_INVALIDA = frozenset(
    {401, 402, 403, 406}
)

OBSERVACIONES_MINIMAS = 3
ENFRIAMIENTO = timedelta(minutes=10)
VENTANA_INTENTOS = timedelta(hours=1)
MAX_INTENTOS_VENTANA = 3

# TNL-WHATSAPP-MANUAL-RECONNECT-V1
# Reconexión desde el panel: basta con que haya pasado este tiempo
# desde el último intento, manual o automático.
ENFRIAMIENTO_MANUAL = timedelta(seconds=60)

# Segundos que se espera el candado del estado.
ESPERA_CANDADO_PASADA = 90
ESPERA_CANDADO_MANUAL = 3

ENV_RUTA_ESTADO = "TNL_WHATSAPP_WATCHDOG_STATE"
RUTA_ESTADO_PREDETERMINADA = (
    "/var/lib/tnl-whatsapp-watchdog/estado.json"
)

VERSION_ESTADO = 1


def ruta_estado() -> str:

    return (
        os.environ.get(ENV_RUTA_ESTADO)
        or RUTA_ESTADO_PREDETERMINADA
    )


# =============================================================================
# Clasificación
# =============================================================================

def clasificar_instancia(
    *,
    estado_vivo,
    metadatos,
) -> str:
    """
    estado_vivo: estado de /instance/connectionState.
    metadatos:   resumen de fetchInstances (owner_present,
                 disconnection_reason) o None.
    """

    estado = str(
        estado_vivo
        or ""
    ).strip().lower()

    if estado == "open":
        return HEALTHY

    if (
        estado not in ("connecting", "close")
        or not isinstance(metadatos, dict)
        or "owner_present" not in metadatos
    ):
        return UNKNOWN

    if (
        metadatos.get("disconnection_reason")
        in MOTIVOS_SESION_INVALIDA
    ):
        return REQUIRES_HUMAN

    # Nunca vinculada (o QR vencido sin escanear).
    if not metadatos.get("owner_present"):
        return REQUIRES_HUMAN

    if estado == "connecting":
        return RECOVERABLE_CONNECTING

    return RECOVERABLE_CLOSE


def respuesta_requiere_emparejamiento(
    data,
) -> bool:
    """
    True si /instance/connect devolvió material de vinculación
    (QR o código). Su contenido nunca se guarda ni se registra.
    """

    if EvolutionClient.extract_qr(data):
        return True

    def buscar(valor):

        if isinstance(valor, dict):

            for clave, contenido in valor.items():

                if (
                    clave in ("pairingCode", "code")
                    and isinstance(contenido, str)
                    and contenido.strip()
                ):
                    return True

                if buscar(contenido):
                    return True

        elif isinstance(valor, list):

            return any(
                buscar(contenido)
                for contenido in valor
            )

        return False

    return buscar(data)


# =============================================================================
# Estado anti-bucle (sin migración)
# =============================================================================

def _iso(momento):

    return (
        momento.astimezone(dt_timezone.utc).isoformat()
        if momento
        else None
    )


def _desde_iso(texto):

    if not texto:
        return None

    momento = datetime.fromisoformat(texto)

    if momento.tzinfo is None:
        raise ValueError("fecha sin zona horaria")

    return momento


def _entrada_vacia() -> dict:

    return {
        "consecutivos": 0,
        "ultimo_estado": "",
        "ultima_clasificacion": "",
        "ultimo_intento": None,
        "intentos": [],
        "requiere_humano": False,
        "actualizado": None,
    }


def _validar_entrada(entrada) -> dict:
    """Devuelve una copia limpia o lanza ValueError."""

    if not isinstance(entrada, dict):
        raise ValueError("entrada inválida")

    limpia = _entrada_vacia()

    consecutivos = entrada.get("consecutivos", 0)

    if (
        not isinstance(consecutivos, int)
        or isinstance(consecutivos, bool)
        or consecutivos < 0
    ):
        raise ValueError("consecutivos inválido")

    intentos = entrada.get("intentos", [])

    if not isinstance(intentos, list):
        raise ValueError("intentos inválido")

    for momento in [entrada.get("ultimo_intento")] + intentos:
        _desde_iso(momento)

    limpia.update(
        {
            "consecutivos": consecutivos,
            "ultimo_estado": str(entrada.get("ultimo_estado") or ""),
            "ultima_clasificacion": str(entrada.get("ultima_clasificacion") or ""),
            "ultimo_intento": entrada.get("ultimo_intento"),
            "intentos": list(intentos),
            "requiere_humano": bool(entrada.get("requiere_humano")),
            "actualizado": entrada.get("actualizado"),
        }
    )

    return limpia


def _intentar_candado(descriptor) -> bool:

    if fcntl is None:
        try:
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False

    return True


def _soltar_candado(descriptor):

    if fcntl is None:
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(descriptor, fcntl.LOCK_UN)


class EstadoWatchdogMemoria:
    """Almacén en memoria (pruebas)."""

    def __init__(self, instancias=None, *, ocupado=False):

        self.instancias = json.loads(
            json.dumps(instancias or {})
        )

        self.ocupado = ocupado

    def bloquear(self, *, espera):

        if self.ocupado:
            return None

        return lambda: None

    def cargar(self):

        return (
            json.loads(json.dumps(self.instancias)),
            False,
        )

    def guardar(self, instancias):

        self.instancias = json.loads(
            json.dumps(instancias)
        )


class EstadoWatchdogArchivo:
    """
    Estado en un archivo JSON, con escritura atómica
    (archivo temporal + os.replace) y permisos 0600.
    """

    def __init__(self, ruta):

        self.ruta = Path(ruta)

    def bloquear(self, *, espera):
        """
        Candado exclusivo entre la pasada del timer y la reconexión
        manual del panel (varios workers de gunicorn), para que ninguna
        escritura pise a la otra. Devuelve la función que lo libera, o
        None si sigue ocupado tras `espera` segundos. El sistema lo
        libera solo si el proceso muere.
        """

        self.ruta.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        descriptor = os.open(
            f"{self.ruta}.lock",
            os.O_RDWR | os.O_CREAT,
            0o600,
        )

        limite = time.monotonic() + espera

        try:
            while not _intentar_candado(descriptor):

                if time.monotonic() >= limite:
                    os.close(descriptor)
                    return None

                time.sleep(0.2)

        except BaseException:
            os.close(descriptor)
            raise

        def liberar():
            try:
                _soltar_candado(descriptor)
            finally:
                os.close(descriptor)

        return liberar

    def cargar(self):
        """
        Devuelve (instancias, corrupto). Un archivo ilegible o con
        estructura inválida NUNCA se interpreta: se ignora completo.
        """

        try:
            texto = self.ruta.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}, False
        except (OSError, UnicodeDecodeError):
            return {}, True

        try:
            datos = json.loads(texto)

            if (
                not isinstance(datos, dict)
                or datos.get("version") != VERSION_ESTADO
                or not isinstance(datos.get("instancias"), dict)
            ):
                raise ValueError("estructura inválida")

            return (
                {
                    str(nombre): _validar_entrada(entrada)
                    for nombre, entrada
                    in datos["instancias"].items()
                },
                False,
            )

        except (ValueError, TypeError):
            return {}, True

    def guardar(self, instancias):

        self.ruta.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        contenido = json.dumps(
            {
                "version": VERSION_ESTADO,
                "instancias": instancias,
            },
            sort_keys=True,
            indent=2,
        )

        descriptor, temporal = tempfile.mkstemp(
            prefix=".estado-",
            suffix=".tmp",
            dir=str(self.ruta.parent),
        )

        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
                archivo.write(contenido)
                archivo.flush()
                os.fsync(archivo.fileno())

            os.chmod(temporal, 0o600)
            os.replace(temporal, self.ruta)

        except BaseException:
            try:
                os.unlink(temporal)
            except OSError:
                pass
            raise


# =============================================================================
# Canales elegibles
# =============================================================================

def instancia_administrada(canal):
    """
    Nombre de la instancia Evolution de un canal WhatsApp activo, con
    Bot activo, de una empresa operativa y con un identificador
    administrado y consistente; None si no cumple.

    El nombre sale sólo de la configuración validada del Canal.
    """

    from core.services.client_connection_reset import (
        ConnectionResetError as CanalWhatsappInvalido,
        _resolver_instance_channel,
    )

    from core.services.client_lifecycle import (
        empresa_operativa,
    )

    empresa = canal.bot.empresa

    if (
        canal.tipo != "whatsapp"
        or not canal.activo
        or not canal.bot.activo
        or not empresa_operativa(empresa)
    ):
        return None

    try:
        nombre = _resolver_instance_channel(canal)
    except CanalWhatsappInvalido:
        return None

    if (
        not nombre
        or nombre != str(canal.identificador).strip()
        or not re.fullmatch(
            rf"tnl-e{empresa.id}-i[0-9]+",
            nombre,
        )
    ):
        return None

    return nombre


def canales_elegibles() -> list:
    """
    Canales WhatsApp activos, con Bot activo, de empresas operativas
    y con un identificador administrado y consistente.

    El nombre de instancia sale sólo de la configuración validada.
    """

    from core.models import Canal

    elegibles = []
    vistos = set()

    canales = (
        Canal.objects
        .select_related(
            "bot",
            "bot__empresa",
        )
        .filter(
            tipo="whatsapp",
            activo=True,
            bot__activo=True,
        )
        .exclude(
            identificador="",
        )
        .order_by("id")
    )

    for canal in canales:

        nombre = instancia_administrada(canal)

        if not nombre or nombre in vistos:
            continue

        vistos.add(nombre)

        elegibles.append(
            {
                "canal_id": canal.id,
                "instancia": nombre,
            }
        )

    return elegibles


# =============================================================================
# Pasada
# =============================================================================

def _crear_cliente():

    return EvolutionClient()


def ejecutar_pasada(
    *,
    dry_run=False,
    cliente=None,
    almacen=None,
    ahora=None,
) -> dict:
    """
    Revisa una vez todos los canales elegibles.

    dry_run: consulta y clasifica, pero no reinicia, no reconecta
    y no guarda estado.
    """

    ahora = ahora or datetime.now(dt_timezone.utc)

    resumen = {
        "checked": 0,
        "healthy": 0,
        "recoverable": 0,
        "recovered": 0,
        "human_required": 0,
        "unknown": 0,
        "errors": 0,
        "dry_run": bool(dry_run),
        "state_corrupt": False,
    }

    resultados = []

    canales = canales_elegibles()

    if not canales:
        return {
            "resumen": resumen,
            "instancias": resultados,
        }

    almacen = almacen or EstadoWatchdogArchivo(ruta_estado())

    # TNL-WHATSAPP-MANUAL-RECONNECT-V1
    # El panel también escribe este estado; sin el candado la pasada
    # sólo observa y no escribe nada.
    liberar = None

    if not dry_run:

        try:
            liberar = almacen.bloquear(espera=ESPERA_CANDADO_PASADA)
        except Exception:
            liberar = None

        if liberar is None:
            resumen["errors"] += 1

    try:
        return _revisar_canales(
            canales=canales,
            dry_run=dry_run,
            sin_candado=not dry_run and liberar is None,
            cliente=cliente,
            almacen=almacen,
            ahora=ahora,
            resumen=resumen,
        )
    finally:
        if liberar is not None:
            liberar()


def _metadatos_evolution(cliente) -> dict:
    """Resumen de fetchInstances por nombre (sin JIDs ni tokens)."""

    metadatos = {}

    for item in EvolutionClient._items(cliente.fetch_instances()):

        resumen_item = EvolutionClient._summary(item)

        if resumen_item:
            metadatos[resumen_item["name"]] = resumen_item

    return metadatos


def _revisar_canales(
    *,
    canales,
    dry_run,
    sin_candado,
    cliente,
    almacen,
    ahora,
    resumen,
) -> dict:

    resultados = []

    estado_instancias, corrupto = almacen.cargar()

    # Con estado corrupto no se sabe cuándo fue el último intento:
    # esta pasada sólo observa y reescribe un estado limpio.
    resumen["state_corrupt"] = corrupto

    try:
        cliente = cliente or _crear_cliente()
    except Exception:
        cliente = None
        resumen["errors"] += 1

    metadatos = {}
    evolution_disponible = False

    if cliente is not None:

        try:
            metadatos = _metadatos_evolution(cliente)
            evolution_disponible = True
        except Exception:
            resumen["errors"] += 1

    for canal in canales:

        nombre = canal["instancia"]
        resumen["checked"] += 1

        entrada = estado_instancias.get(nombre) or _entrada_vacia()

        estado_vivo = None

        if evolution_disponible:
            try:
                estado_vivo = cliente.connection_state(nombre)["state"]
            except Exception:
                resumen["errors"] += 1

        clasificacion = (
            clasificar_instancia(
                estado_vivo=estado_vivo,
                metadatos=metadatos.get(nombre),
            )
            if estado_vivo
            else UNKNOWN
        )

        if clasificacion == HEALTHY:
            # Se conservan ultimo_intento e intentos: una recuperación
            # breve no reinicia el enfriamiento ni el límite por hora.
            entrada["consecutivos"] = 0
            entrada["requiere_humano"] = False
        else:
            entrada["consecutivos"] += 1

        if (
            clasificacion in RECUPERABLES
            and entrada["requiere_humano"]
        ):
            clasificacion = REQUIRES_HUMAN

        if clasificacion == REQUIRES_HUMAN:
            entrada["requiere_humano"] = True

        entrada["intentos"] = [
            momento
            for momento in entrada["intentos"]
            if ahora - _desde_iso(momento) < VENTANA_INTENTOS
        ]

        accion = "none"

        if clasificacion in RECUPERABLES:

            ultimo_intento = _desde_iso(entrada["ultimo_intento"])

            if entrada["consecutivos"] < OBSERVACIONES_MINIMAS:
                accion = "observing"
            elif ultimo_intento and ahora - ultimo_intento < ENFRIAMIENTO:
                accion = "cooldown"
            elif len(entrada["intentos"]) >= MAX_INTENTOS_VENTANA:
                accion = "hourly_limit"
            elif dry_run:
                accion = "dry_run"
            elif corrupto:
                accion = "state_corrupt"
            elif sin_candado:
                accion = "state_locked"
            else:
                accion, clasificacion = _recuperar(
                    cliente=cliente,
                    almacen=almacen,
                    estado_instancias=estado_instancias,
                    nombre=nombre,
                    entrada=entrada,
                    clasificacion=clasificacion,
                    ahora=ahora,
                )

                if accion in ("error", "state_not_saved"):
                    resumen["errors"] += 1

        entrada["ultimo_estado"] = estado_vivo or "desconocido"
        entrada["ultima_clasificacion"] = clasificacion
        entrada["actualizado"] = _iso(ahora)
        estado_instancias[nombre] = entrada

        if clasificacion == HEALTHY:
            resumen["healthy"] += 1
        elif clasificacion in RECUPERABLES:
            resumen["recoverable"] += 1
        elif clasificacion == REQUIRES_HUMAN:
            resumen["human_required"] += 1
        else:
            resumen["unknown"] += 1

        if accion in ("restart", "connect"):
            resumen["recovered"] += 1

        resultados.append(
            {
                "instancia": nombre,
                "estado": estado_vivo or "desconocido",
                "clasificacion": clasificacion,
                "accion": accion,
                "consecutivos": entrada["consecutivos"],
            }
        )

    if not dry_run and not sin_candado:

        nombres = {canal["instancia"] for canal in canales}

        try:
            almacen.guardar(
                {
                    nombre: entrada
                    for nombre, entrada in estado_instancias.items()
                    if nombre in nombres
                }
            )
        except Exception:
            resumen["errors"] += 1

    return {
        "resumen": resumen,
        "instancias": resultados,
    }


def _recuperar(
    *,
    cliente,
    almacen,
    estado_instancias,
    nombre,
    entrada,
    clasificacion,
    ahora,
):
    """
    Registra el intento ANTES de actuar (si no se puede guardar,
    no se actúa) y ejecuta una sola acción segura.
    """

    entrada["ultimo_intento"] = _iso(ahora)
    entrada["intentos"].append(_iso(ahora))
    estado_instancias[nombre] = entrada

    try:
        almacen.guardar(estado_instancias)
    except Exception:
        return "state_not_saved", clasificacion

    try:

        if clasificacion == RECOVERABLE_CONNECTING:
            cliente.restart_instance(nombre)
            return "restart", clasificacion

        respuesta = cliente.connect_instance(nombre)

        if respuesta_requiere_emparejamiento(respuesta):
            entrada["requiere_humano"] = True
            return "pairing_required", REQUIRES_HUMAN

        return "connect", clasificacion

    except Exception:
        return "error", clasificacion


# =============================================================================
# Panel: reconexión manual y estado visible
# TNL-WHATSAPP-MANUAL-RECONNECT-V1
# =============================================================================

def reconectar_instancia_manual(
    *,
    canal,
    cliente=None,
    almacen=None,
    ahora=None,
) -> dict:
    """
    Reconexión pedida desde el panel para un Canal ya cargado por la
    vista. Reutiliza la clasificación, el estado anti-bucle y
    _recuperar() del watchdog.

    Frente a la pasada automática no espera 3 observaciones, ni los
    10 minutos, ni el límite por hora (la pide una persona), pero exige
    ENFRIAMIENTO_MANUAL desde el último intento, manual o automático, y
    registra el suyo en el mismo estado: el timer no actúa encima
    durante su enfriamiento normal.

    Devuelve {"resultado", "clasificacion"} y nunca datos de Evolution.
    Resultados: canal_no_configurado, canal_inactivo, en_curso,
    estado_no_disponible, evolution_no_disponible, conectado,
    requiere_vinculacion, estado_desconocido, enfriamiento,
    reinicio_solicitado, reconexion_solicitada, error_evolution.
    """

    from core.services.client_lifecycle import (
        empresa_operativa,
    )

    ahora = ahora or datetime.now(dt_timezone.utc)

    def resultado(codigo, clasificacion=None):
        return {
            "resultado": codigo,
            "clasificacion": clasificacion,
        }

    if canal.tipo != "whatsapp":
        return resultado("canal_no_configurado")

    if not (
        canal.activo
        and canal.bot.activo
        and empresa_operativa(canal.bot.empresa)
    ):
        return resultado("canal_inactivo")

    nombre = instancia_administrada(canal)

    if not nombre:
        return resultado("canal_no_configurado")

    almacen = almacen or EstadoWatchdogArchivo(ruta_estado())

    try:
        liberar = almacen.bloquear(espera=ESPERA_CANDADO_MANUAL)
    except Exception:
        return resultado("estado_no_disponible")

    # Otra reconexión (doble clic, otro worker) o la pasada del timer.
    if liberar is None:
        return resultado("en_curso")

    try:

        estado_instancias, corrupto = almacen.cargar()

        if corrupto:
            return resultado("estado_no_disponible")

        entrada = estado_instancias.get(nombre) or _entrada_vacia()

        try:
            cliente = cliente or _crear_cliente()
            metadatos = _metadatos_evolution(cliente).get(nombre)
            estado_vivo = cliente.connection_state(nombre)["state"]
        except Exception:
            return resultado("evolution_no_disponible", UNKNOWN)

        clasificacion = clasificar_instancia(
            estado_vivo=estado_vivo,
            metadatos=metadatos,
        )

        if (
            clasificacion in RECUPERABLES
            and entrada["requiere_humano"]
        ):
            clasificacion = REQUIRES_HUMAN

        if clasificacion == HEALTHY:
            return resultado("conectado", clasificacion)

        if clasificacion == REQUIRES_HUMAN:
            return resultado("requiere_vinculacion", clasificacion)

        if clasificacion == UNKNOWN:
            return resultado("estado_desconocido", clasificacion)

        ultimo_intento = _desde_iso(entrada["ultimo_intento"])

        if ultimo_intento and ahora - ultimo_intento < ENFRIAMIENTO_MANUAL:
            return resultado("enfriamiento", clasificacion)

        entrada["intentos"] = [
            momento
            for momento in entrada["intentos"]
            if ahora - _desde_iso(momento) < VENTANA_INTENTOS
        ]

        accion, clasificacion = _recuperar(
            cliente=cliente,
            almacen=almacen,
            estado_instancias=estado_instancias,
            nombre=nombre,
            entrada=entrada,
            clasificacion=clasificacion,
            ahora=ahora,
        )

        if accion == "pairing_required":

            entrada["actualizado"] = _iso(ahora)

            try:
                almacen.guardar(estado_instancias)
            except Exception:
                # El intento ya quedó guardado; el timer volverá a
                # marcar la vinculación pendiente en su pasada.
                pass

            return resultado("requiere_vinculacion", clasificacion)

        return resultado(
            {
                "restart": "reinicio_solicitado",
                "connect": "reconexion_solicitada",
                "state_not_saved": "estado_no_disponible",
            }.get(accion, "error_evolution"),
            clasificacion,
        )

    finally:
        liberar()


ESTADOS_PANEL = {
    HEALTHY: ("conectado", "Conectado"),
    RECOVERABLE_CONNECTING: ("conectando", "Conectando"),
    RECOVERABLE_CLOSE: ("desconectado", "Desconectado"),
    REQUIRES_HUMAN: ("requiere_vinculacion", "Requiere vinculación"),
    UNKNOWN: ("no_disponible", "Estado no disponible"),
}


def estado_panel(
    *,
    cliente,
    nombre,
    metadatos,
    almacen=None,
) -> dict:
    """
    Estado VIVO de una instancia en palabras simples para el panel.
    Sólo lectura: consulta connectionState y lee el estado del watchdog.
    """

    try:
        estado_vivo = cliente.connection_state(nombre)["state"]
    except Exception:
        estado_vivo = None

    clasificacion = (
        clasificar_instancia(
            estado_vivo=estado_vivo,
            metadatos=metadatos,
        )
        if estado_vivo
        else UNKNOWN
    )

    # Vinculación pendiente ya detectada por el watchdog (QR).
    if clasificacion in RECUPERABLES:

        instancias, _ = (
            almacen or EstadoWatchdogArchivo(ruta_estado())
        ).cargar()

        if (instancias.get(nombre) or {}).get("requiere_humano"):
            clasificacion = REQUIRES_HUMAN

    codigo, texto = ESTADOS_PANEL[clasificacion]

    return {
        "codigo": codigo,
        "texto": texto,
    }
