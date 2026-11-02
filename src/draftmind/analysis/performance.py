"""Puntuación de rendimiento de una partida (0-10), comparando a los 10 jugadores.

Método propio y transparente (no es el «OP Score» de OP.GG, cuyo cálculo no
es público):
1. Para cada jugador se calculan seis métricas de la partida: KDA,
   participación en asesinatos, cuota de daño a campeones de su equipo, oro
   por minuto, CS por minuto y visión por minuto.
2. En cada métrica se le da una posición relativa entre los 10 (0 = el peor,
   1 = el mejor; los empates comparten valor).
3. La puntuación es la media de esas posiciones × 10.
Los soportes no se penalizan por CS: para ellos esa métrica no cuenta.
MVP = mejor puntuación del equipo ganador; ACE = mejor del perdedor.

Es una COMPARACIÓN DENTRO DE LA PARTIDA: no mide si jugaste bien o mal en
términos absolutos, ni tiene en cuenta decisiones o el contexto.
"""

from dataclasses import dataclass
from statistics import mean

from draftmind.domain.enums import Role


@dataclass
class ParticipantLine:
    key: str            # Identificador único dentro de la partida (puuid o participantId).
    team_id: int
    win: bool
    role: Role | None
    kills: int
    deaths: int
    assists: int
    damage: int
    gold: int
    cs: int
    vision: int


@dataclass
class PerformanceResult:
    score: float        # 0-10
    rank: int           # 1 = mejor de la partida
    badge: str | None   # "MVP", "ACE" o None


def _percentiles(values: list[float]) -> list[float]:
    """Posición relativa de cada valor entre 0 y 1 (empates con el mismo valor)."""
    n = len(values)
    if n < 2:
        return [0.5] * n
    ordered = sorted(values)
    return [mean(i for i, v in enumerate(ordered) if v == value) / (n - 1) for value in values]


def score_match(lines: list[ParticipantLine], minutes: float) -> dict[str, PerformanceResult]:
    if len(lines) < 2 or minutes <= 0:
        return {}
    team_kills = {t: sum(p.kills for p in lines if p.team_id == t) for t in {p.team_id for p in lines}}
    team_damage = {t: sum(p.damage for p in lines if p.team_id == t) for t in team_kills}

    metrics = {
        "kda": [(p.kills + p.assists) / max(p.deaths, 1) for p in lines],
        "kp": [(p.kills + p.assists) / team_kills[p.team_id] if team_kills[p.team_id] else 0 for p in lines],
        "damage": [p.damage / team_damage[p.team_id] if team_damage[p.team_id] else 0 for p in lines],
        "gold": [p.gold / minutes for p in lines],
        "cs": [p.cs / minutes for p in lines],
        "vision": [p.vision / minutes for p in lines],
    }
    ranks = {name: _percentiles(values) for name, values in metrics.items()}
    scores = []
    for i, p in enumerate(lines):
        used = [name for name in metrics if not (name == "cs" and p.role is Role.UTILITY)]
        scores.append(round(10 * mean(ranks[name][i] for name in used), 1))

    order = sorted(range(len(lines)), key=lambda i: -scores[i])
    result = {}
    for i, p in enumerate(lines):
        same_team = [j for j in order if lines[j].team_id == p.team_id]
        badge = None
        if same_team[0] == i:
            badge = "MVP" if p.win else "ACE"
        result[p.key] = PerformanceResult(score=scores[i], rank=order.index(i) + 1, badge=badge)
    return result
