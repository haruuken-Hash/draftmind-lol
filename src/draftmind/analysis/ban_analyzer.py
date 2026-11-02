"""Sugerencias de bloqueo personalizadas.

No hay estadísticas globales (como las de OP.GG o iTero), así que se combinan
tres fuentes, cada una con su etiqueta:
1. TUS PARTIDAS (estadística observada): rivales directos contra los que
   has perdido más de la mitad de las veces. Con pocas partidas pesa poco.
2. PERFILES (inferencia): campeones de tu posición cuyo perfil pone en
   aprietos a tus campeones de confianza (más presión temprana, iniciación
   contra campeones sin desenganche...).
3. ESTADÍSTICAS IMPORTADAS (observada, si hay): enfrentamientos con win rate
   por debajo del 48 % y al menos 100 partidas.
Un bloqueo nunca es obligatorio: es una sugerencia para pensar.
"""

from pydantic import BaseModel, Field

from draftmind.analysis.champion_stats import valid_matches
from draftmind.analysis.confidence import MIN_SAMPLE
from draftmind.domain.enums import EvidenceKind, ProfileOrigin, Role
from draftmind.domain.models import ChampionProfile, MatchSummary
from draftmind.integrations.statistics_providers import StatisticsProvider

PERSONAL_FULL_WEIGHT_GAMES = 6
PROFILE_WEIGHT = 0.5
ESTIMATED_FACTOR = 0.6
IMPORTED_THRESHOLD = 0.48


class BanSuggestion(BaseModel):
    champion_id: str
    score: float
    reasons: list[str] = Field(default_factory=list)
    kinds: list[EvidenceKind] = Field(default_factory=list)
    games: int = 0          # Partidas tuyas contra él.


def _profile_threat(opp: ChampionProfile, mine: ChampionProfile) -> tuple[float, list[str]]:
    threat, why = 0.0, []
    if opp.early - mine.early >= 2:
        threat += 0.5
        why.append(f"mucha más presión temprana que {mine.name}")
    if opp.scaling - mine.scaling >= 2:
        threat += 0.3
        why.append(f"escala mejor que {mine.name}")
    if opp.engage >= 2 and mine.disengage == 0 and mine.frontline <= 1:
        threat += 0.3
        why.append(f"puede iniciar sobre {mine.name}, que no tiene desenganche")
    if opp.cc >= 3 and mine.resource_dependence == 3 and mine.frontline == 0:
        threat += 0.2
        why.append(f"mucho control contra un {mine.name} frágil")
    return threat, why


def suggest_bans(
    role: Role | None,
    pool: list[str],
    matches: list[MatchSummary],
    profiles: dict[str, ChampionProfile],
    imported: StatisticsProvider | None = None,
    exclude: set[str] | None = None,
    limit: int = 5,
) -> list[BanSuggestion]:
    exclude = exclude or set()
    suggestions: dict[str, BanSuggestion] = {}

    def get(champion_id: str) -> BanSuggestion:
        return suggestions.setdefault(champion_id, BanSuggestion(champion_id=champion_id, score=0))

    # 1. Tus partidas.
    record: dict[str, list[bool]] = {}
    for m in valid_matches(matches):
        if m.lane_opponent and (role is None or m.role is role):
            record.setdefault(m.lane_opponent, []).append(bool(m.win))
    for opp, results in record.items():
        losses, games = results.count(False), len(results)
        if games >= 2 and losses / games > 0.5:
            s = get(opp)
            s.score += (losses / games - 0.5) * 2 * min(games, PERSONAL_FULL_WEIGHT_GAMES) / PERSONAL_FULL_WEIGHT_GAMES
            s.games = games
            s.reasons.append(f"Has perdido {losses} de {games} partidas contra él como rival directo"
                             + (" (muestra muy pequeña)" if games < 10 else ""))
            s.kinds.append(EvidenceKind.OBSERVED)

    # 2. Perfiles: amenaza para tus campeones de confianza.
    my_profiles = [profiles[c] for c in pool if c in profiles]
    if my_profiles:
        for opp in profiles.values():
            if opp.id in pool or (role is not None and role not in opp.roles):
                continue
            total, reasons = 0.0, []
            for mine in my_profiles:
                threat, why = _profile_threat(opp, mine)
                total += threat
                reasons += why
            if total <= 0:
                continue
            factor = ESTIMATED_FACTOR if opp.origin is ProfileOrigin.ESTIMATED else 1.0
            s = get(opp.id)
            s.score += PROFILE_WEIGHT * factor * total / len(my_profiles)
            s.reasons.append("Según los perfiles: " + "; ".join(dict.fromkeys(reasons)))
            s.kinds.append(EvidenceKind.INFERENCE)

    # 3. Estadísticas importadas con muestra suficiente.
    if imported is not None:
        for mine in pool:
            for stat in imported.opponents(mine, role):
                wr = stat.observed_win_rate
                if stat.opponent_id and wr is not None and stat.games >= MIN_SAMPLE and wr < IMPORTED_THRESHOLD:
                    s = get(stat.opponent_id)
                    s.score += (0.5 - wr) * 10
                    s.reasons.append(f"{stat.source.name}: {mine} gana el {wr:.0%} contra él "
                                     f"({stat.games} partidas, parche {stat.patch})")
                    s.kinds.append(EvidenceKind.OBSERVED)

    result = [s for s in suggestions.values() if s.champion_id not in exclude and s.score > 0]
    return sorted(result, key=lambda s: -s.score)[:limit]
