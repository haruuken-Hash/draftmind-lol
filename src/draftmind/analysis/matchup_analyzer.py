"""Análisis de un enfrentamiento directo (tu campeón contra el rival de tu línea).

Separa tres cosas:
1. Lo OBSERVADO: win rate de una fuente, con su muestra, parche y fecha.
2. La DIFERENCIA respecto a una referencia (tu win rate general con ese
   campeón en la misma fuente, o 50 % si no hay otra).
3. La INFERENCIA cualitativa: condiciones en que el enfrentamiento puede
   inclinarse hacia un lado, según los perfiles de demostración.

Una diferencia estadística no demuestra causalidad y ningún campeón es un
«counter» absoluto; los textos lo expresan como condiciones.
"""

from datetime import datetime, timezone

from pydantic import BaseModel

from draftmind.analysis.confidence import assess_confidence
from draftmind.domain.enums import ConfidenceLevel, DamageType, EvidenceKind, ExperienceLevel, Role
from draftmind.domain.models import ChampionProfile, ChampionStat, ConfidenceAssessment, UserProfile
from draftmind.integrations.statistics_providers import StatisticsProvider, consistency_warnings

NEUTRAL_REFERENCE = 0.5


class StatEvidence(BaseModel):
    stat: ChampionStat
    win_rate: float | None
    reference: float
    reference_label: str
    difference_pp: float | None   # Puntos porcentuales respecto a la referencia.
    confidence: ConfidenceAssessment
    text: str


class Insight(BaseModel):
    kind: EvidenceKind
    text: str


class MatchupAnalysis(BaseModel):
    champion_id: str
    opponent_id: str
    role: Role | None
    evidence: list[StatEvidence]
    insights: list[Insight]
    confidence: ConfidenceAssessment
    warnings: list[str]


def patch_of(version: str | None) -> str | None:
    """'16.21.1' -> '16.21'."""
    if not version:
        return None
    return ".".join(version.split(".")[:2])


def evaluate_stat(stat: ChampionStat, reference: ChampionStat | None, current_patch: str | None,
                  now: datetime | None = None) -> StatEvidence:
    now = now or datetime.now(timezone.utc)
    wr = stat.observed_win_rate
    if reference is not None and reference.observed_win_rate is not None and reference.games > stat.games:
        ref_value = reference.observed_win_rate
        ref_label = f"win rate general del campeón en la misma fuente ({reference.games} partidas)"
    else:
        ref_value, ref_label = NEUTRAL_REFERENCE, "50 % (sin otra referencia disponible)"
    same_patch = None
    if current_patch and stat.patch:
        same_patch = patch_of(stat.patch) == current_patch
    age = (now - stat.source.retrieved_at).total_seconds() / 86400 if stat.source.retrieved_at else None
    confidence = assess_confidence(
        has_data=stat.games > 0, is_statistical=True, sample_size=stat.games,
        same_patch=same_patch, data_age_days=age,
    )
    diff = (wr - ref_value) * 100 if wr is not None else None
    if wr is None:
        text = f"{stat.source.name}: {stat.games} partidas, pero la fuente no ofrece el resultado."
    else:
        text = (
            f"{stat.source.name}: {wr:.0%} de victorias en {stat.games} partidas"
            f"{f' (parche {stat.patch})' if stat.patch else ''}. "
            f"Diferencia respecto a la referencia ({ref_label}): {diff:+.1f} puntos. "
            "Una diferencia estadística no demuestra que el enfrentamiento sea la causa."
        )
    return StatEvidence(stat=stat, win_rate=wr, reference=ref_value, reference_label=ref_label,
                        difference_pp=diff, confidence=confidence, text=text)


def qualitative_insights(c: ChampionProfile, o: ChampionProfile, user: UserProfile) -> list[Insight]:
    """Condiciones en que el enfrentamiento puede ser favorable o desfavorable."""
    out: list[Insight] = []

    def add(text: str, kind: EvidenceKind = EvidenceKind.INFERENCE):
        out.append(Insight(kind=kind, text=text))

    if c.early > o.early:
        add(f"{c.name} tiene más presión temprana en los perfiles ({c.early}/3 frente a {o.early}/3): "
            "la fase de líneas puede inclinarse a tu favor si la aprovechas antes de que el rival escale.")
    elif c.early < o.early:
        add(f"{o.name} tiene más presión temprana ({o.early}/3 frente a {c.early}/3): puede convenir "
            "jugar con prudencia hasta completar tus primeros objetos.")
    if c.scaling > o.scaling:
        add(f"{c.name} escala mejor ({c.scaling}/3 frente a {o.scaling}/3): las partidas largas pueden favorecerte.")
    elif c.scaling < o.scaling:
        add(f"{o.name} escala mejor ({o.scaling}/3 frente a {c.scaling}/3): si la partida se alarga, "
            "tu ventaja relativa puede disminuir.")
    if o.engage >= 2 and c.disengage >= 2:
        add("Tus herramientas de desenganche pueden neutralizar sus intentos de iniciación.")
    elif o.engage >= 2 and c.disengage == 0 and c.frontline <= 1:
        add("Puedes ser vulnerable a sus iniciaciones: la posición y la visión cobran más importancia.")
    if c.cc >= o.cc + 2:
        add("Tienes bastante más control de masas: las jugadas coordinadas con tu jungla pueden ser más efectivas.")
    if c.frontline >= 2 and o.damage_type is not DamageType.MIXED:
        resist = "armadura" if o.damage_type is DamageType.PHYSICAL else "resistencia mágica"
        add(f"El daño de {o.name} es principalmente {o.damage_type.label.lower()}: priorizar {resist} "
            "puede ayudarte en la línea.", EvidenceKind.EDUCATIONAL)
    if c.difficulty == 3 and user.experience is ExperienceLevel.BEGINNER:
        add(f"{c.name} tiene dificultad alta para tu nivel declarado: el resultado depende mucho de la "
            "ejecución, más que del enfrentamiento en sí.", EvidenceKind.EDUCATIONAL)
    if not out:
        add("Los perfiles de ambos campeones son parecidos: el enfrentamiento depende sobre todo de la ejecución.")
    return out


def analyze_matchup(
    champion_id: str,
    opponent_id: str,
    role: Role | None,
    providers: list[StatisticsProvider],
    profiles: dict[str, ChampionProfile],
    user: UserProfile,
    current_patch: str | None,
    now: datetime | None = None,
) -> MatchupAnalysis:
    evidence: list[StatEvidence] = []
    for provider in providers:
        reference = next(iter(provider.champion_stats(champion_id, role)), None)
        for stat in provider.matchup_stats(champion_id, opponent_id, role):
            evidence.append(evaluate_stat(stat, reference, current_patch, now))

    insights: list[Insight] = []
    c, o = profiles.get(champion_id), profiles.get(opponent_id)
    if c and o:
        insights = qualitative_insights(c, o, user)
    else:
        missing = [x for x, p in ((champion_id, c), (opponent_id, o)) if p is None]
        insights.append(Insight(kind=EvidenceKind.INSUFFICIENT,
                                text=f"Sin perfil cualitativo para {', '.join(missing)}: no hay análisis cualitativo."))

    usable = [e for e in evidence if e.confidence.level is not ConfidenceLevel.INSUFFICIENT]
    if usable:
        best = max(usable, key=lambda e: e.stat.games)
        confidence = best.confidence
    elif evidence:
        confidence = ConfidenceAssessment(
            level=ConfidenceLevel.INSUFFICIENT,
            reasons=[f"Hay {sum(e.stat.games for e in evidence)} partidas observadas: muestra insuficiente "
                     "para una conclusión estadística."],
        )
    else:
        confidence = assess_confidence(has_data=bool(c and o), is_statistical=False)
        if c and o:
            confidence.reasons.append("No hay estadísticas de este enfrentamiento en las fuentes conectadas.")

    warnings = consistency_warnings([e.stat for e in evidence])
    warnings += [w for e in evidence for w in e.confidence.warnings]
    return MatchupAnalysis(
        champion_id=champion_id, opponent_id=opponent_id, role=role, evidence=evidence,
        insights=insights, confidence=confidence, warnings=list(dict.fromkeys(warnings)),
    )
