"""Reúne los proveedores de estadísticas activos."""

import shutil
from pathlib import Path

from draftmind.domain.enums import Role
from draftmind.domain.models import ChampionStat, MatchSummary
from draftmind.integrations.statistics_providers import (
    ImportedStatsProvider,
    PersonalStatsProvider,
    StatisticsProvider,
)


class StatsService:
    def __init__(self, import_path: Path):
        self.import_path = import_path
        self.personal: PersonalStatsProvider | None = None
        self.imported: ImportedStatsProvider | None = None
        self.import_error: str | None = None
        if import_path.exists():
            try:
                self.imported = ImportedStatsProvider.from_file(import_path)
            except Exception as exc:  # El archivo guardado se dañó: se informa, no se bloquea.
                self.import_error = str(exc)

    @property
    def providers(self) -> list[StatisticsProvider]:
        return [p for p in (self.personal, self.imported) if p is not None]

    def set_matches(self, matches: list[MatchSummary], demo: bool, region: str | None) -> None:
        self.personal = PersonalStatsProvider(matches, demo, region) if matches else None

    def import_file(self, path: Path) -> ImportedStatsProvider:
        """Valida el archivo y, si es correcto, guarda una copia en la carpeta de datos."""
        provider = ImportedStatsProvider.from_file(path)
        self.import_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, self.import_path)
        self.imported = provider
        self.import_error = None
        return provider

    def remove_import(self) -> None:
        self.import_path.unlink(missing_ok=True)
        self.imported = None

    def matchup_stats(self, champion_id: str, opponent_id: str, role: Role | None) -> list[ChampionStat]:
        return [s for p in self.providers for s in p.matchup_stats(champion_id, opponent_id, role)]
