"""Proveedores de estadísticas intercambiables.

No existe (que se haya podido verificar) una API pública y gratuita de
estadísticas agregadas cuyo uso permita reutilizar los datos: OP.GG o U.GG no
documentan una. Por eso hay dos proveedores:

1. ``PersonalStatsProvider``: calcula tus propias estadísticas a partir de
   las partidas descargadas con la API oficial de Riot. Son datos reales,
   pero con muestras pequeñas.
2. ``ImportedStatsProvider``: lee un archivo JSON preparado por el usuario a
   partir de una fuente que permita reutilizar sus datos. El archivo debe
   identificar la fuente, el parche y la fecha de consulta.

Para añadir una fuente nueva basta con heredar de ``StatisticsProvider``.
"""

import json
from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from draftmind.domain.enums import EvidenceKind, Role
from draftmind.domain.models import ChampionStat, DataSource, MatchSummary


class StatisticsProvider(ABC):
    name: str

    @abstractmethod
    def champion_stats(self, champion_id: str, role: Role | None = None) -> list[ChampionStat]:
        """Estadísticas generales del campeón (sin rival concreto)."""

    @abstractmethod
    def matchup_stats(self, champion_id: str, opponent_id: str, role: Role | None = None) -> list[ChampionStat]:
        """Estadísticas del campeón contra un rival directo."""

    def opponents(self, champion_id: str, role: Role | None = None) -> list[ChampionStat]:
        """Todos los enfrentamientos observados del campeón (opcional)."""
        return []


# --- Estadísticas personales ---------------------------------------------------

class PersonalStatsProvider(StatisticsProvider):
    name = "Tus partidas"

    def __init__(self, matches: Iterable[MatchSummary], demo: bool, region: str | None):
        self._matches = [m for m in matches if m.win is not None and (m.duration_s or 0) >= 300]
        patches = sorted({m.patch for m in self._matches if m.patch})
        self._patch = patches[0] if len(patches) == 1 else None
        self.mixed_patches = len(patches) > 1
        self.patches = patches
        self._source = DataSource(
            name="Partidas FICTICIAS de demostración" if demo else "Tus partidas (Riot API, match-v5)",
            kind=EvidenceKind.OBSERVED,
            patch=self._patch,
            retrieved_at=datetime.now(timezone.utc),
            notes=(("Varios parches mezclados: " + ", ".join(patches) + ". ") if self.mixed_patches else "")
            + "Solo reflejan tus partidas: no representan al conjunto de jugadores.",
        )
        self._region = region

    @property
    def source(self) -> DataSource:
        return self._source

    def _stat(self, games: list[MatchSummary], champion_id: str, role: Role | None, opponent: str | None) -> ChampionStat:
        return ChampionStat(
            champion_id=champion_id, role=role, opponent_id=opponent, games=len(games),
            wins=sum(1 for g in games if g.win), patch=self._patch, region=self._region,
            rank_segment="Tus partidas", source=self._source,
        )

    def _select(self, champion_id: str, role: Role | None) -> list[MatchSummary]:
        return [m for m in self._matches if m.champion_id == champion_id and (role is None or m.role is role)]

    def champion_stats(self, champion_id, role=None):
        games = self._select(champion_id, role)
        return [self._stat(games, champion_id, role, None)] if games else []

    def matchup_stats(self, champion_id, opponent_id, role=None):
        games = [m for m in self._select(champion_id, role) if m.lane_opponent == opponent_id]
        return [self._stat(games, champion_id, role, opponent_id)] if games else []

    def opponents(self, champion_id, role=None):
        by_opponent: dict[str, list[MatchSummary]] = {}
        for m in self._select(champion_id, role):
            if m.lane_opponent:
                by_opponent.setdefault(m.lane_opponent, []).append(m)
        return sorted(
            (self._stat(g, champion_id, role, opp) for opp, g in by_opponent.items()),
            key=lambda s: -s.games,
        )


# --- Estadísticas importadas ---------------------------------------------------------

class ImportedRow(BaseModel):
    champion_id: str
    games: int = Field(ge=0)
    role: Role | None = None
    opponent_id: str | None = None
    wins: int | None = Field(default=None, ge=0)
    win_rate: float | None = Field(default=None, ge=0, le=1)
    pick_rate: float | None = Field(default=None, ge=0, le=1)
    ban_rate: float | None = Field(default=None, ge=0, le=1)


class ImportedSource(BaseModel):
    name: str
    url: str
    retrieved_at: datetime
    notes: str = ""


class ImportedFile(BaseModel):
    """Formato del archivo de importación (ver docs/data_sources.md)."""

    source: ImportedSource
    patch: str
    region: str | None = None
    rank_segment: str | None = None
    rows: list[ImportedRow]


class StatsImportError(Exception):
    pass


class ImportedStatsProvider(StatisticsProvider):
    def __init__(self, data: ImportedFile):
        self.data = data
        self.name = data.source.name
        self._source = DataSource(
            name=data.source.name, kind=EvidenceKind.OBSERVED, url=data.source.url,
            patch=data.patch, retrieved_at=data.source.retrieved_at,
            notes=data.source.notes or "Datos importados por el usuario.",
        )

    @classmethod
    def from_file(cls, path: Path) -> "ImportedStatsProvider":
        try:
            return cls(ImportedFile.model_validate(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError) as exc:
            raise StatsImportError(f"No se pudo leer el archivo: {exc}") from exc
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(p) for p in first["loc"])
            raise StatsImportError(f"El archivo no tiene el formato esperado ({where}: {first['msg']}).") from exc

    def _to_stat(self, row: ImportedRow) -> ChampionStat:
        return ChampionStat(
            champion_id=row.champion_id, games=row.games, role=row.role, opponent_id=row.opponent_id,
            wins=row.wins, win_rate=row.win_rate, pick_rate=row.pick_rate, ban_rate=row.ban_rate,
            patch=self.data.patch, region=self.data.region, rank_segment=self.data.rank_segment,
            source=self._source,
        )

    def _rows(self, champion_id, role, opponent_id):
        return [
            self._to_stat(r) for r in self.data.rows
            if r.champion_id == champion_id and r.opponent_id == opponent_id
            and (role is None or r.role is None or r.role is role)
        ]

    def champion_stats(self, champion_id, role=None):
        return self._rows(champion_id, role, None)

    def matchup_stats(self, champion_id, opponent_id, role=None):
        return self._rows(champion_id, role, opponent_id)

    def opponents(self, champion_id, role=None):
        return [self._to_stat(r) for r in self.data.rows
                if r.champion_id == champion_id and r.opponent_id and (role is None or r.role in (None, role))]


def consistency_warnings(stats: list[ChampionStat]) -> list[str]:
    """Avisos cuando se comparan datos de parches, regiones o segmentos distintos."""
    warnings = []
    for attr, label in (("patch", "parches"), ("region", "regiones"), ("rank_segment", "segmentos de jugadores")):
        values = {getattr(s, attr) for s in stats if getattr(s, attr)}
        if len(values) > 1:
            warnings.append(f"Se comparan datos de {label} distintos: {', '.join(sorted(values))}.")
    return warnings
