"""Configuración leída de variables de entorno (y de un archivo .env opcional).

La clave de Riot se guarda en memoria, pero nunca se muestra ni se registra:
``__repr__`` la oculta para que no aparezca por accidente en un log.
"""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# En el ejecutable de PyInstaller el .env se busca junto al .exe; en
# desarrollo, en la raíz del proyecto.
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    log_level: str = "INFO"
    ddragon_language: str = "es_MX"
    ddragon_enabled: bool = True  # False = no usar la red (útil en pruebas).
    riot_api_key: str | None = field(default=None, repr=False)

    @property
    def has_riot_api_key(self) -> bool:
        return bool(self.riot_api_key)

    @property
    def demo_mode(self) -> bool:
        return not self.has_riot_api_key

    @property
    def database_path(self) -> Path:
        return self.data_dir / "draftmind.db"

    @property
    def ddragon_cache_dir(self) -> Path:
        return self.data_dir / "cache" / "ddragon"


def _default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "DraftMindLoL"


def load_settings(env_file: Path | None = None) -> Settings:
    # override=False: una variable ya definida en el sistema tiene prioridad.
    load_dotenv(env_file or PROJECT_ROOT / ".env", override=False)
    data_dir = os.environ.get("DRAFTMIND_DATA_DIR", "").strip()
    return Settings(
        data_dir=Path(data_dir) if data_dir else _default_data_dir(),
        log_level=os.environ.get("DRAFTMIND_LOG_LEVEL", "INFO").strip().upper() or "INFO",
        ddragon_language=os.environ.get("DRAFTMIND_LANGUAGE", "").strip() or "es_MX",
        riot_api_key=os.environ.get("RIOT_API_KEY", "").strip() or None,
    )
