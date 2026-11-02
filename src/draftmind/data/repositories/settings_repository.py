"""Preferencias de la aplicación guardadas en SQLite."""

from pathlib import Path

from sqlalchemy.orm import sessionmaker

from draftmind.data.database import AppSettingRow
from draftmind.integrations.league_client import DEFAULT_INSTALL_DIR

LIVE_ENABLED = "live_draft_enabled"
LEAGUE_DIR = "league_install_dir"


class SettingsRepository:
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def get(self, key: str, default: str = "") -> str:
        with self._session_factory() as session:
            row = session.get(AppSettingRow, key)
            return row.value if row else default

    def set(self, key: str, value: str) -> None:
        with self._session_factory() as session:
            session.merge(AppSettingRow(key=key, value=value))
            session.commit()

    # --- Draft en vivo (desactivado por defecto) -------------------------------

    @property
    def live_draft_enabled(self) -> bool:
        return self.get(LIVE_ENABLED, "0") == "1"

    @live_draft_enabled.setter
    def live_draft_enabled(self, enabled: bool) -> None:
        self.set(LIVE_ENABLED, "1" if enabled else "0")

    @property
    def league_install_dir(self) -> Path:
        return Path(self.get(LEAGUE_DIR, str(DEFAULT_INSTALL_DIR)))

    @league_install_dir.setter
    def league_install_dir(self, path: Path) -> None:
        self.set(LEAGUE_DIR, str(path))
