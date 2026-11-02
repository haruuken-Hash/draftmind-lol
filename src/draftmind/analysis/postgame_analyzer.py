"""Métricas y observaciones postpartida.

Las métricas se calculan solo si existen sus datos de partida. Las
observaciones describen tendencias medibles y proponen preguntas de
reflexión; nunca concluyen que el jugador tomó una mala decisión, porque
una métrica aislada no permite saberlo.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import mean

from draftmind.domain.enums import EvidenceKind, Role
from draftmind.domain.models import MatchSummary, Observation

REMAKE_MAX_SECONDS = 300   # Partidas más cortas: posibles remakes, fuera de tendencias.
TREND_WINDOW = 5           # Partidas recientes frente a las 5 anteriores.
MIN_TREND_SAMPLE = 3


def kda(m: MatchSummary) -> float | None:
    """(asesinatos + asistencias) / muertes. Con 0 muertes se divide entre 1."""
    if None in (m.kills, m.deaths, m.assists):
        return None
    return (m.kills + m.assists) / max(m.deaths, 1)


def cs_per_min(m: MatchSummary) -> float | None:
    if m.cs is None or not m.duration_s:
        return None
    return m.cs / (m.duration_s / 60)


def kill_participation(m: MatchSummary) -> float | None:
    """Proporción de los asesinatos del equipo en que participó (0-1)."""
    if None in (m.kills, m.assists, m.team_kills) or m.team_kills == 0:
        return None
    return min(1.0, (m.kills + m.assists) / m.team_kills)


def is_probable_remake(m: MatchSummary) -> bool:
    return m.duration_s is not None and m.duration_s < REMAKE_MAX_SECONDS


@dataclass
class MatchFilter:
    champion_id: str | None = None
    role: Role | None = None
    days: int | None = None      # None = sin límite.
    win: bool | None = None      # None = todas.

    def apply(self, matches: list[MatchSummary], now: datetime | None = None) -> list[MatchSummary]:
        now = now or datetime.now(timezone.utc)
        result = []
        for m in matches:
            if self.champion_id and m.champion_id != self.champion_id:
                continue
            if self.role and m.role is not self.role:
                continue
            if self.win is not None and m.win is not self.win:
                continue
            if self.days is not None and (m.played_at is None or now - m.played_at > timedelta(days=self.days)):
                continue
            result.append(m)
        return result


def _avg(values) -> float | None:
    values = [v for v in values if v is not None]
    return mean(values) if values else None


def _trend(matches: list[MatchSummary], metric, label: str, fmt: str, higher_is_better: bool,
           question: str) -> Observation | None:
    """Compara las TREND_WINDOW partidas más recientes con las anteriores."""
    ordered = sorted((m for m in matches if m.played_at), key=lambda m: m.played_at, reverse=True)
    recent = [v for v in map(metric, ordered[:TREND_WINDOW]) if v is not None]
    previous = [v for v in map(metric, ordered[TREND_WINDOW:TREND_WINDOW * 2]) if v is not None]
    if len(recent) < MIN_TREND_SAMPLE or len(previous) < MIN_TREND_SAMPLE:
        return None
    now_avg, before_avg = mean(recent), mean(previous)
    change = now_avg - before_avg
    if before_avg and abs(change) / abs(before_avg) < 0.1:
        direction = "se mantiene estable"
    else:
        improved = (change > 0) == higher_is_better
        direction = "ha mejorado" if improved else "ha empeorado"
    return Observation(
        kind=EvidenceKind.OBSERVED,
        text=(f"{label} {direction}: {fmt.format(now_avg)} de media en tus últimas {len(recent)} partidas "
              f"frente a {fmt.format(before_avg)} en las {len(previous)} anteriores. {question}"),
        sample_size=len(recent) + len(previous),
    )


def observations(matches: list[MatchSummary]) -> list[Observation]:
    valid = [m for m in matches if not is_probable_remake(m)]
    if not valid:
        return [Observation(kind=EvidenceKind.INSUFFICIENT,
                            text="No hay partidas suficientes para generar observaciones.")]

    result: list[Observation] = []
    decided = [m for m in valid if m.win is not None]
    if decided:
        wins = sum(m.win for m in decided)
        result.append(Observation(
            kind=EvidenceKind.OBSERVED,
            text=f"Resultado: {wins} victorias de {len(decided)} partidas ({wins / len(decided):.0%}). "
                 "Con pocas partidas este porcentaje varía mucho por azar.",
            sample_size=len(decided),
        ))

    non_support = [m for m in valid if m.role is not Role.UTILITY]
    trends = [
        _trend(non_support, cs_per_min, "Tu CS por minuto (sin contar soporte)", "{:.1f}", True,
               "¿En qué momentos de la partida dejas de farmear: al rotar, al agruparte, tras morir?"),
        _trend(valid, lambda m: m.deaths, "Tus muertes por partida", "{:.1f}", False,
               "Revisa en la repetición si tus muertes se repiten en situaciones parecidas."),
        _trend(valid, lambda m: (m.vision_score / (m.duration_s / 60)) if m.vision_score is not None and m.duration_s else None,
               "Tu puntuación de visión por minuto", "{:.2f}", True,
               "¿Colocas y despejas guardianes antes de los objetivos importantes?"),
        _trend(valid, kill_participation, "Tu participación en asesinatos", "{:.0%}", True,
               "¿Llegas a tiempo a las peleas que tu equipo provoca?"),
    ]
    found = [t for t in trends if t]
    result += found
    if not found:
        result.append(Observation(
            kind=EvidenceKind.INSUFFICIENT,
            text=f"Para comparar tendencias hacen falta al menos {MIN_TREND_SAMPLE * 2} partidas con datos completos.",
        ))

    by_champion: dict[str, list[MatchSummary]] = {}
    for m in decided:
        by_champion.setdefault(m.champion_id, []).append(m)
    if by_champion:
        top, games = max(by_champion.items(), key=lambda kv: len(kv[1]))
        wins = sum(g.win for g in games)
        result.append(Observation(
            kind=EvidenceKind.OBSERVED,
            text=f"Tu campeón más jugado en esta selección es {top}: {len(games)} partidas, "
                 f"{wins} victorias. " + ("Muestra muy pequeña para sacar conclusiones." if len(games) < 10 else ""),
            sample_size=len(games),
        ))
    result.append(Observation(
        kind=EvidenceKind.EDUCATIONAL,
        text="Estas cifras describen resultados, no decisiones. Para entender por qué ocurrieron, "
             "revisa la repetición de la partida.",
    ))
    return result


def averages(matches: list[MatchSummary]) -> dict[str, float | None]:
    valid = [m for m in matches if not is_probable_remake(m)]
    return {
        "kda": _avg(map(kda, valid)),
        "cs_per_min": _avg(map(cs_per_min, valid)),
        "kill_participation": _avg(map(kill_participation, valid)),
        "vision": _avg(m.vision_score for m in valid),
        "deaths": _avg(m.deaths for m in valid),
    }
