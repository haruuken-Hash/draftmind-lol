"""Estadísticas personales por campeón y por posición (como el perfil de OP.GG).

Todo sale de tus partidas descargadas; los posibles remakes no cuentan.
"""

from collections import Counter
from statistics import mean

from pydantic import BaseModel

from draftmind.analysis.postgame_analyzer import cs_per_min, is_probable_remake, kda, kill_participation
from draftmind.domain.enums import Role
from draftmind.domain.models import MatchSummary


class ChampionPerformance(BaseModel):
    champion_id: str
    games: int
    wins: int
    kda: float | None
    cs_per_min: float | None
    kill_participation: float | None
    avg_score: float | None
    mvp_or_ace: int = 0

    @property
    def win_rate(self) -> float:
        return self.wins / self.games if self.games else 0.0


def _avg(values) -> float | None:
    values = [v for v in values if v is not None]
    return mean(values) if values else None


def valid_matches(matches: list[MatchSummary]) -> list[MatchSummary]:
    return [m for m in matches if not is_probable_remake(m) and m.win is not None]


def champion_performance(matches: list[MatchSummary], role: Role | None = None) -> list[ChampionPerformance]:
    groups: dict[str, list[MatchSummary]] = {}
    for m in valid_matches(matches):
        if role is None or m.role is role:
            groups.setdefault(m.champion_id, []).append(m)
    result = [
        ChampionPerformance(
            champion_id=champ, games=len(games), wins=sum(1 for g in games if g.win),
            kda=_avg(map(kda, games)), cs_per_min=_avg(map(cs_per_min, games)),
            kill_participation=_avg(map(kill_participation, games)),
            avg_score=_avg(g.performance_score for g in games),
            mvp_or_ace=sum(1 for g in games if g.badge),
        )
        for champ, games in groups.items()
    ]
    return sorted(result, key=lambda c: (-c.games, -c.win_rate))


def role_distribution(matches: list[MatchSummary]) -> Counter:
    return Counter(m.role for m in valid_matches(matches) if m.role is not None)


def comfort_pool(matches: list[MatchSummary], role: Role | None, mastery_ids: list[str],
                 limit: int = 3) -> list[str]:
    """Tus campeones de confianza: los más jugados en esa posición; si no hay
    partidas, los de más maestría."""
    played = [c.champion_id for c in champion_performance(matches, role)][:limit]
    if played:
        return played
    return mastery_ids[:limit]


def recent_form(matches: list[MatchSummary], count: int = 20) -> list[bool]:
    """Resultados más recientes primero (True = victoria)."""
    return [bool(m.win) for m in valid_matches(matches)[:count]]
