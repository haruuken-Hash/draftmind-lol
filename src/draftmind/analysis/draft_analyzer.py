"""Analizador de draft cualitativo.

Para cada candidato se evalúan varios criterios ("factores"). Cada factor
acumula notas con un signo (+ favorable, - desfavorable) y una explicación.
Así cada ventaja o desventaja que ve el usuario tiene detrás una regla
concreta y localizable en este archivo.

Limitación importante de esta etapa: no hay estadísticas de enfrentamientos.
El factor de enfrentamiento lo declara explícitamente en lugar de inventarlas.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from statistics import mean

from draftmind.analysis.composition_analyzer import (
    HIGH_CC,
    HIGH_ENGAGE,
    LOW_FRONTLINE,
    analyze_team,
    damage_shares,
)
from draftmind.analysis.confidence import assess_confidence
from draftmind.analysis.matchup_analyzer import evaluate_stat
from draftmind.domain.enums import (
    ConfidenceLevel,
    DamageType,
    EvidenceKind,
    ExperienceLevel,
    ProfileOrigin,
    Role,
)
from draftmind.domain.models import (
    CandidateAnalysis,
    ChampionProfile,
    ChampionStat,
    DataSource,
    DraftPick,
    DraftState,
    FactorResult,
    TeamProfile,
    UserProfile,
)

WEIGHTS = {
    "role": 1.0,
    "synergy": 1.0,
    "threats": 1.0,
    "tempo": 0.75,
    "matchup": 0.5,  # Peso bajo: solo hay comparación cualitativa.
    "preferences": 0.75,
    "comfort": 1.0,
}

# Peso de los factores cualitativos cuando el candidato tiene un perfil estimado
# automáticamente (comparado con los 26 editoriales, la estimación coincide en el
# valor exacto en torno a la mitad de las veces y casi siempre queda a ±1).
ESTIMATED_WEIGHT = 0.6

LABELS = {
    "role": "Encaje de rol",
    "synergy": "Sinergia con aliados",
    "threats": "Respuesta a la composición enemiga",
    "tempo": "Ventanas de poder",
    "matchup": "Enfrentamiento directo",
    "preferences": "Preferencias personales",
    "comfort": "Tu experiencia con el campeón",
}


@dataclass
class ComfortStats:
    """Tu historial con un campeón: partidas descargadas en esa posición y maestría."""

    games: int = 0
    wins: int = 0
    mastery_level: int | None = None
    mastery_points: int | None = None


COMFORT_MIN_GAMES_FOR_WR = 5
COMFORT_MIN_GAMES_IN_ROLE = 3


@dataclass
class _Factor:
    """Acumulador de notas de un factor antes de convertirlo en FactorResult."""

    key: str
    kind: EvidenceKind = EvidenceKind.INFERENCE
    notes: list[tuple[float, str]] = field(default_factory=list)

    def add(self, delta: float, text: str) -> None:
        self.notes.append((delta, text))

    def result(self, neutral_text: str) -> FactorResult:
        score = max(-2.0, min(2.0, sum(d for d, _ in self.notes)))
        explanation = " ".join(t for _, t in self.notes) or neutral_text
        return FactorResult(
            key=self.key,
            label=LABELS[self.key],
            score=score,
            weight=WEIGHTS[self.key],
            explanation=explanation,
            kind=self.kind,
        )


class DraftAnalyzer:
    def __init__(
        self,
        champions: list[ChampionProfile],
        source: DataSource,
        profile: UserProfile | None = None,
    ):
        self._champions = {c.id: c for c in champions}
        self._source = source
        self.profile = profile or UserProfile()
        # Opcional: función que devuelve estadísticas observadas de un enfrentamiento.
        self.matchup_stats: Callable[[str, str, Role | None], list[ChampionStat]] | None = None
        self.current_patch: str | None = None
        # Opcional: tu historial con un campeón en una posición (partidas y maestría).
        self.comfort: Callable[[str, Role | None], ComfortStats | None] | None = None

    def set_champions(self, champions: list[ChampionProfile]) -> None:
        """Sustituye los perfiles (p. ej. tras descargar Data Dragon o revisar uno)."""
        self._champions = {c.id: c for c in champions}

    # --- Consultas básicas -------------------------------------------------

    @property
    def champions(self) -> list[ChampionProfile]:
        return sorted(self._champions.values(), key=lambda c: c.name)

    def has_profile(self, champion_id: str) -> bool:
        return champion_id in self._champions

    def missing_profiles(self, draft: DraftState) -> list[str]:
        """Campeones del draft sin perfil cualitativo (no entran en el análisis)."""
        ids = [p.champion_id for p in draft.allies + draft.enemies]
        if draft.my_champion_id:
            ids.append(draft.my_champion_id)
        return [i for i in ids if i not in self._champions]

    def champion(self, champion_id: str) -> ChampionProfile:
        try:
            return self._champions[champion_id]
        except KeyError:
            raise ValueError(f"Campeón desconocido en los datos cargados: {champion_id}") from None

    def _profiles(self, picks: list[DraftPick]) -> list[ChampionProfile]:
        return [self._champions[p.champion_id] for p in picks if p.champion_id in self._champions]

    # --- Composición -------------------------------------------------------

    def compositions(self, draft: DraftState) -> tuple[TeamProfile, TeamProfile]:
        """Perfil del equipo aliado (incluido tu campeón, si lo hay) y del enemigo."""
        allies = self._profiles(draft.allies)
        if draft.my_champion_id in self._champions:
            allies.append(self._champions[draft.my_champion_id])
        return analyze_team(allies), analyze_team(self._profiles(draft.enemies))

    # --- Análisis de candidatos -------------------------------------------

    def analyze_candidate(self, draft: DraftState, candidate_id: str) -> CandidateAnalysis:
        c = self.champion(candidate_id)
        allies = self._profiles([p for p in draft.allies if p.champion_id != candidate_id])
        enemies = self._profiles(draft.enemies)

        factors = [
            self._role_fit(c, draft.my_role),
            self._synergy(c, allies),
            self._threats(c, enemies),
            self._tempo(c, allies, enemies),
            self._matchup(c, draft),
            self._preferences(c),
            self._comfort(c, draft.my_role),
        ]
        # Un perfil estimado es menos fiable: sus factores cualitativos pesan menos
        # (las estadísticas observadas, no).
        def factor_weight(f: FactorResult) -> float:
            estimated = c.origin is ProfileOrigin.ESTIMATED and f.kind is not EvidenceKind.OBSERVED
            return f.weight * (ESTIMATED_WEIGHT if estimated else 1.0)

        weighted = sum(f.score * factor_weight(f) for f in factors)
        score = round(max(0.0, min(100.0, 50 + 10 * weighted)), 1)

        pros, cons = [], []
        for f in factors:
            if f.kind is EvidenceKind.INSUFFICIENT:
                continue
            if f.score > 0:
                pros.append(f"{f.label}: {f.explanation}")
            elif f.score < 0:
                cons.append(f"{f.label}: {f.explanation}")

        confidence = assess_confidence(has_data=True, is_statistical=False)
        if not allies and not enemies:
            confidence.reasons.append("El draft está vacío: el análisis apenas tiene contexto.")
        estimated = [p.name for p in [c, *allies, *enemies] if p.origin is ProfileOrigin.ESTIMATED]
        if estimated:
            confidence.warnings.append(
                "Perfiles estimados automáticamente a partir de la clase y las valoraciones oficiales "
                f"(menos fiables; puedes revisarlos en «Campeones»): {', '.join(estimated)}."
            )
        if any(p.origin is ProfileOrigin.EDITORIAL for p in [c, *allies, *enemies]) and self._source.patch is None:
            confidence.warnings.append(
                "Los perfiles editoriales de demostración no tienen parche asociado: no reflejan "
                "necesariamente el estado actual del juego."
            )

        return CandidateAnalysis(
            champion=c,
            score=score,
            factors=factors,
            pros=pros,
            cons=cons,
            confidence=confidence,
            sources=[self._source],
        )

    def suggest_candidates(
        self, draft: DraftState, role: Role | None = None, limit: int = 5
    ) -> list[CandidateAnalysis]:
        """Candidatos para un rol ordenados por la puntuación cualitativa.

        No es una clasificación por win rate: solo refleja los criterios
        de este módulo y debe leerse junto con sus explicaciones.
        """
        role = role or draft.my_role
        taken = {p.champion_id for p in draft.allies + draft.enemies} | set(draft.bans)
        pool = [
            c for c in self._champions.values()
            if c.id not in taken and (role is None or role in c.roles or self._plays_in_role(c.id, role))
        ]
        analyses = [self.analyze_candidate(draft, c.id) for c in pool]
        analyses.sort(key=lambda a: (-a.score, a.champion.name))
        return analyses[:limit]

    # --- Factores ----------------------------------------------------------

    def _plays_in_role(self, champion_id: str, role: Role) -> bool:
        stats = self.comfort(champion_id, role) if self.comfort else None
        return bool(stats and stats.games >= COMFORT_MIN_GAMES_IN_ROLE)

    def _role_fit(self, c: ChampionProfile, role: Role | None) -> FactorResult:
        f = _Factor("role")
        if role is None:
            f.kind = EvidenceKind.INSUFFICIENT
            return f.result("No has indicado tu posición; no se evalúa el encaje de rol.")
        if role in c.roles:
            f.add(1.0, f"{c.name} figura como {role.label} en los perfiles.")
        elif self._plays_in_role(c.id, role):
            f.add(1.0, f"Tú lo juegas como {role.label} en tus partidas.")
        else:
            f.add(-1.5, f"{c.name} no figura como {role.label}; sería una elección poco habitual.")
        return f.result("")

    def _synergy(self, c: ChampionProfile, allies: list[ChampionProfile]) -> FactorResult:
        f = _Factor("synergy")
        if not allies:
            f.kind = EvidenceKind.INSUFFICIENT
            return f.result("Sin aliados conocidos no se puede evaluar la sinergia.")

        has_frontline = any(a.frontline >= 2 for a in allies)
        has_engage = any(a.engage >= 2 for a in allies)
        if not has_frontline and c.frontline >= 2:
            f.add(1.0, "Aporta la primera línea que no tienen los aliados conocidos.")
        elif not has_frontline and c.frontline == 0 and len(allies) >= 3:
            f.add(-0.5, "El equipo seguiría sin primera línea clara.")
        if not has_engage and c.engage >= 2:
            f.add(1.0, "Aporta iniciación que el equipo no tiene.")

        if len(allies) >= 2:
            physical, magic = damage_shares(allies)
            if physical >= 0.75:
                if c.damage_type is DamageType.MAGIC:
                    f.add(0.75, "Equilibra el daño de un equipo mayoritariamente físico.")
                elif c.damage_type is DamageType.PHYSICAL:
                    f.add(-0.75, "Concentra aún más el daño físico del equipo.")
            elif magic >= 0.75:
                if c.damage_type is DamageType.PHYSICAL:
                    f.add(0.75, "Equilibra el daño de un equipo mayoritariamente mágico.")
                elif c.damage_type is DamageType.MAGIC:
                    f.add(-0.75, "Concentra aún más el daño mágico del equipo.")

        hungry_allies = sum(1 for a in allies if a.resource_dependence == 3)
        if hungry_allies >= 2 and c.resource_dependence == 3:
            f.add(-0.5, "Ya hay varios aliados que necesitan mucho oro; competirían por recursos.")
        return f.result("Encaje neutro con los aliados conocidos.")

    def _threats(self, c: ChampionProfile, enemies: list[ChampionProfile]) -> FactorResult:
        f = _Factor("threats")
        if not enemies:
            f.kind = EvidenceKind.INSUFFICIENT
            return f.result("Sin enemigos conocidos no se pueden evaluar amenazas.")

        enemy = analyze_team(enemies)
        if enemy.engage >= HIGH_ENGAGE:
            if c.disengage >= 2:
                f.add(1.0, "Sus herramientas de desenganche ayudan contra la iniciación enemiga.")
            elif c.frontline == 0 and c.disengage == 0:
                f.add(-0.75, "No aporta aguante ni desenganche frente a mucha iniciación enemiga.")
        if len(enemies) >= 3 and enemy.frontline < LOW_FRONTLINE and c.engage >= 2:
            f.add(0.5, "El rival tiene poca primera línea: una buena iniciación puede alcanzar a sus objetivos frágiles.")
        if enemy.cc >= HIGH_CC and c.resource_dependence == 3 and c.frontline == 0:
            f.add(-0.5, "Mucho control de masas enemigo para un campeón frágil que necesita recursos.")
        return f.result("No se detectan amenazas o respuestas destacables con los datos disponibles.")

    def _tempo(
        self, c: ChampionProfile, allies: list[ChampionProfile], enemies: list[ChampionProfile]
    ) -> FactorResult:
        f = _Factor("tempo")
        if not allies and not enemies:
            f.kind = EvidenceKind.INSUFFICIENT
            return f.result("Sin campeones conocidos no se pueden comparar ventanas de poder.")

        if enemies and mean(e.early for e in enemies) >= 2 and c.early <= 1 and c.scaling >= 2:
            f.add(-0.5, "El rival muestra presión temprana; las primeras fases pueden ser difíciles.")
        if len(allies) >= 2:
            ally_early = mean(a.early for a in allies)
            ally_scaling = mean(a.scaling for a in allies)
            if ally_scaling - ally_early >= 1 and c.early >= 2:
                f.add(0.5, "Añade presión temprana a un equipo orientado al escalado.")
            elif ally_early - ally_scaling >= 1 and c.scaling >= 2:
                f.add(0.5, "Aporta escalado a un equipo con mucha presión temprana.")
        return f.result("Sin desequilibrios claros de ventanas de poder.")

    def _matchup(self, c: ChampionProfile, draft: DraftState) -> FactorResult:
        f = _Factor("matchup")
        opponent_pick = next(
            (p for p in draft.enemies if draft.my_role is not None and p.role is draft.my_role),
            None,
        )
        if opponent_pick is None:
            f.kind = EvidenceKind.INSUFFICIENT
            return f.result("No se conoce el rival directo (indica tu posición y el rol del enemigo).")
        stats_note = "Sin estadísticas de enfrentamiento disponibles (evidencia insuficiente)."
        if self.matchup_stats is not None:
            stats = self.matchup_stats(c.id, opponent_pick.champion_id, draft.my_role)
            if stats:
                best = max(stats, key=lambda s: s.games)
                evidence = evaluate_stat(best, None, self.current_patch)
                if evidence.confidence.level is not ConfidenceLevel.INSUFFICIENT and evidence.difference_pp is not None:
                    f.kind = EvidenceKind.OBSERVED
                    f.add(max(-1.0, min(1.0, evidence.difference_pp / 10)),
                          f"{evidence.text} Confianza: {evidence.confidence.level.label.lower()}.")
                    return f.result("")
                stats_note = (f"Hay {best.games} partidas observadas en «{best.source.name}», "
                              "pero la muestra es insuficiente para usarla.")

        opponent = self._champions.get(opponent_pick.champion_id)
        if opponent is None:
            f.kind = EvidenceKind.INSUFFICIENT
            return f.result(f"{stats_note} El rival directo no tiene perfil cualitativo en los datos de demostración.")

        diff = c.early - opponent.early
        f.add(
            max(-0.5, min(0.5, diff * 0.25)),
            f"{stats_note} Comparación cualitativa: presión temprana {c.early}/3 de {c.name} frente a "
            f"{opponent.early}/3 de {opponent.name}. Es una pista, no demuestra el resultado de la línea.",
        )
        return f.result("")

    def _comfort(self, c: ChampionProfile, role: Role | None) -> FactorResult:
        """Experiencia real: partidas tuyas con el campeón (en esa posición) y maestría."""
        f = _Factor("comfort", kind=EvidenceKind.OBSERVED)
        stats = self.comfort(c.id, role) if self.comfort else None
        if stats is None or (stats.games == 0 and not stats.mastery_level):
            f.kind = EvidenceKind.INSUFFICIENT
            where = f" como {role.label}" if role else ""
            return f.result(f"Sin partidas tuyas descargadas con {c.name}{where} ni maestría conocida.")
        if stats.games >= 10:
            f.add(1.0, f"Lo has jugado {stats.games} veces en esta posición.")
        elif stats.games >= 3:
            f.add(0.5, f"Lo has jugado {stats.games} veces en esta posición.")
        elif stats.games:
            f.add(0.0, f"Solo {stats.games} partida(s) tuya(s) con él en esta posición.")
        if stats.games >= COMFORT_MIN_GAMES_FOR_WR:
            wr = stats.wins / stats.games
            f.add(max(-0.75, min(0.75, (wr - 0.5) * 2)),
                  f"Tu win rate con él: {wr:.0%} en {stats.games} partidas"
                  + (" (muestra pequeña)." if stats.games < 20 else "."))
        if stats.mastery_level and stats.mastery_level >= 5:
            points = f" ({stats.mastery_points:,} puntos)".replace(",", ".") if stats.mastery_points else ""
            f.add(0.25, f"Maestría nivel {stats.mastery_level}{points}.")
        return f.result("")

    def _preferences(self, c: ChampionProfile) -> FactorResult:
        f = _Factor("preferences", kind=EvidenceKind.EDUCATIONAL)
        p = self.profile
        if not p.favorite_champions and p.experience is ExperienceLevel.UNSET:
            f.kind = EvidenceKind.INSUFFICIENT
            return f.result("Perfil sin configurar; no se tienen en cuenta preferencias.")
        if c.id in p.favorite_champions:
            f.add(0.75, "Está entre tus campeones preferidos.")
        if p.experience is ExperienceLevel.BEGINNER and c.difficulty == 3:
            f.add(-0.75, "Dificultad alta para tu nivel declarado; conviene practicarlo antes fuera de partidas clasificatorias.")
        return f.result("Sin relación especial con tus preferencias.")
