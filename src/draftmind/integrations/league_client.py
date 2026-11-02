"""Lectura del cliente de LoL (League Client API) — SOLO LECTURA.

Lo que dice Riot (developer.riotgames.com/docs/lol, comprobado el 30/10/2026):
- La League Client API «no tiene soporte oficial» para aplicaciones de
  terceros: no hay garantías de documentación, disponibilidad ni aviso de
  cambios. Puede dejar de funcionar con cualquier parche.
- El cliente usa un certificado autofirmado; Riot publica el certificado raíz
  (incluido en resources/certs/riotgames.pem).

Cómo se conecta: el cliente escribe un archivo «lockfile» en su carpeta de
instalación con el formato  nombre:pid:puerto:contraseña:protocolo. No se
leen otros procesos ni su memoria: solo ese archivo.

Garantías de este módulo:
- Solo existen peticiones GET y solo a las rutas de ALLOWED_PATHS. No hay
  ningún método para elegir, bloquear ni modificar nada en el cliente.
- Solo se conecta a 127.0.0.1.
- La contraseña del lockfile no se registra ni se muestra.
"""

import logging
import ssl
from dataclasses import dataclass, field
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

DEFAULT_INSTALL_DIR = Path(r"C:\Riot Games\League of Legends")
RIOT_ROOT_CERT = Path(__file__).resolve().parents[1] / "resources" / "certs" / "riotgames.pem"

GAMEFLOW_PHASE = "/lol-gameflow/v1/gameflow-phase"
CHAMP_SELECT_SESSION = "/lol-champ-select/v1/session"
ALLOWED_PATHS = frozenset({GAMEFLOW_PHASE, CHAMP_SELECT_SESSION})


class LeagueClientError(Exception):
    """Error comprensible para el usuario."""


@dataclass(frozen=True)
class Lockfile:
    process: str
    pid: int
    port: int
    password: str = field(repr=False)
    protocol: str


def read_lockfile(install_dir: Path) -> Lockfile | None:
    """Devuelve None si el cliente no está abierto (no existe el lockfile)."""
    path = install_dir / "lockfile"
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise LeagueClientError(f"No se pudo leer el lockfile del cliente ({exc.__class__.__name__}).") from None
    parts = text.split(":")
    if len(parts) != 5 or not parts[1].isdigit() or not parts[2].isdigit() or parts[4] not in ("http", "https"):
        raise LeagueClientError("El lockfile del cliente no tiene el formato esperado.")
    return Lockfile(process=parts[0], pid=int(parts[1]), port=int(parts[2]), password=parts[3], protocol=parts[4])


def _verified_context() -> ssl.SSLContext:
    """Valida que el certificado esté firmado por la CA de Riot.

    No se comprueba el nombre del host porque la conexión es siempre a
    127.0.0.1 y no se conoce el nombre que figura en el certificado local.

    Python 3.13 activa por defecto VERIFY_X509_STRICT, que rechaza el
    certificado del cliente por no incluir el campo opcional «Authority Key
    Identifier» (comprobado con el cliente real el 01/11/2026). Se desactiva
    solo esa comprobación estricta: la firma de la CA de Riot sigue
    validándose.
    """
    context = ssl.create_default_context(cafile=str(RIOT_ROOT_CERT))
    context.check_hostname = False
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return context


class LeagueClient:
    def __init__(self, lockfile: Lockfile, http: httpx.Client | None = None):
        self._base = f"{lockfile.protocol}://127.0.0.1:{lockfile.port}"
        self._auth = ("riot", lockfile.password)
        self._custom_http = http is not None
        self._http = http or httpx.Client(timeout=5, verify=_verified_context())
        self.certificate_verified = True

    def _get(self, path: str):
        if path not in ALLOWED_PATHS:
            raise LeagueClientError(f"Ruta no permitida: {path}")  # Lista cerrada, solo lectura.
        try:
            response = self._http.get(f"{self._base}{path}", auth=self._auth)
        except httpx.ConnectError as exc:
            if not self._custom_http and self.certificate_verified and "CERTIFICATE" in str(exc).upper():
                # El certificado local no encaja con la CA publicada: se acepta solo porque
                # la conexión es a 127.0.0.1, y se informa en la interfaz.
                log.warning("El certificado del cliente no se pudo validar; se continúa sin verificación local.")
                self.certificate_verified = False
                self._http = httpx.Client(timeout=5, verify=False)
                return self._get(path)
            raise LeagueClientError("No se pudo conectar con el cliente de LoL (¿se está cerrando?).") from None
        except httpx.HTTPError as exc:
            raise LeagueClientError(f"Error al hablar con el cliente de LoL ({exc.__class__.__name__}).") from None
        if response.status_code == 404:
            return None
        if response.status_code in (401, 403):
            raise LeagueClientError("El cliente rechazó la conexión: puede que el lockfile esté desactualizado.")
        if response.status_code >= 400:
            raise LeagueClientError(f"El cliente respondió con el código {response.status_code}.")
        return response.json()

    def gameflow_phase(self) -> str:
        phase = self._get(GAMEFLOW_PHASE)
        return phase if isinstance(phase, str) else "None"

    def champ_select_session(self) -> dict | None:
        """None si no hay una selección de campeones en curso."""
        session = self._get(CHAMP_SELECT_SESSION)
        return session if isinstance(session, dict) else None
