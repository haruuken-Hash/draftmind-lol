"""Enfrentamiento directo por fases y conveniencia de los gankeos.

No hay estadísticas globales por nivel (las de iTero u OP.GG no son
públicas), así que cada conclusión indica de dónde sale:
- DATOS OFICIALES (Data Dragon): vida, armadura, ataque, velocidad de ataque
  y alcance base. Con ellos se calcula un duelo de ataques básicos a nivel 1
  y cómo crece el aguante. No incluyen habilidades, runas ni objetos.
- PERFILES (inferencia): presión temprana, escalado, iniciación, control...
- TUS PARTIDAS (observado): tu historial contra ese rival y la diferencia de
  oro al minuto 10 (timeline oficial). Suele ser una muestra pequeña.

Se habla de «ventaja probable», nunca de «te gana seguro»: en una partida
real deciden las habilidades, la experiencia y las decisiones.
"""

from pydantic import BaseModel, Field

from draftmind.analysis.champion_stats import valid_matches
from draftmind.domain.enums import EvidenceKind, ProfileOrigin, Role
from draftmind.domain.models import BaseStats, ChampionProfile, DraftPick, MatchSummary, Observation

RANGED_MIN = 300          # Alcance a partir del cual un campeón se considera a distancia.
RANGE_EDGE = 100          # Entre dos campeones a distancia (o dos cuerpo a cuerpo), diferencia que cuenta.
DUEL_MARGIN = 1.15        # Hay que matar un 15 % más rápido para hablar de ventaja.
EDGE_THRESHOLD = 0.5
DURABILITY_LEVELS = (1, 6, 11, 16)
GOOD_GANK = 0.6


class PhaseEdge(BaseModel):
    """Quién tiende a tener ventaja en una fase: +1 tú, 0 parejo, -1 el rival."""

    levels: str
    title: str
    edge: int
    reasons: list[str] = Field(default_factory=list)
    kinds: list[EvidenceKind] = Field(default_factory=list)


class DurabilityRow(BaseModel):
    level: int
    my_hp: float
    enemy_hp: float
    my_armor: float
    enemy_armor: float


class LaneMatchup(BaseModel):
    my_id: str
    enemy_id: str
    role: Role | None
    phases: list[PhaseEdge]
    summary: str
    durability: list[DurabilityRow] = Field(default_factory=list)
    history: Observation
    estimated_profiles: bool = False


class GankOption(BaseModel):
    lane: Role                       # TOP, MIDDLE o BOTTOM (tirador + soporte).
    enemy_ids: list[str]
    score: float
    verdict: str
    reasons: list[str] = Field(default_factory=list)


class GankDanger(BaseModel):
    jungler_id: str
    level: str                       # «alto», «medio» o «bajo».
    reasons: list[str] = Field(default_factory=list)


# --- Posiciones del equipo rival -------------------------------------------

def assign_enemy_roles(picks: list[DraftPick],
                       profiles: dict[str, ChampionProfile]) -> dict[Role, tuple[str, bool]]:
    """Posición -> (campeón, deducida). En el draft en vivo el cliente no dice
    las posiciones rivales: se usan las que indicas y, para el resto, se deducen
    solo cuando el perfil deja una única opción libre."""
    assigned = {p.role: (p.champion_id, False) for p in picks if p.role is not None}
    pending = [p.champion_id for p in picks if p.role is None and p.champion_id in profiles]
    changed = True
    while changed and pending:
        changed = False
        for champion_id in list(pending):
            options = [r for r in profiles[champion_id].roles if r not in assigned]
            if len(options) == 1:
                assigned[options[0]] = (champion_id, True)
                pending.remove(champion_id)
                changed = True
        for role in Role:
            fits = [c for c in pending if role not in assigned and role in profiles[c].roles]
            if len(fits) == 1:
                assigned[role] = (fits[0], True)
                pending.remove(fits[0])
                changed = True
    return assigned


# --- Enfrentamiento por fases ------------------------------------------------

def _edge(score: float) -> int:
    if score >= EDGE_THRESHOLD:
        return 1
    if score <= -EDGE_THRESHOLD:
        return -1
    return 0


def _time_to_kill(attacker: BaseStats, target: BaseStats) -> float:
    """Segundos para derrotar al rival solo con ataques básicos a nivel 1."""
    effective_hp = target.hp * (1 + target.armor / 100)  # Los ataques básicos hacen daño físico.
    return effective_hp / (attacker.attack_damage * attacker.attack_speed)


def _early_phase(mine: ChampionProfile, enemy: ChampionProfile, my_stats: BaseStats | None,
                 enemy_stats: BaseStats | None, role: Role | None) -> PhaseEdge:
    score, reasons, kinds = 0.0, [], [EvidenceKind.INFERENCE]
    diff = mine.early - enemy.early
    score += max(-2, min(2, diff)) * 0.5
    if diff:
        who = "Tú tienes" if diff > 0 else f"{enemy.name} tiene"
        reasons.append(f"{who} más presión temprana según los perfiles ({mine.early} contra {enemy.early}).")
    else:
        reasons.append(f"Presión temprana similar según los perfiles ({mine.early} contra {enemy.early}).")

    if my_stats and enemy_stats:
        kinds.append(EvidenceKind.OFFICIAL)
        if role is not Role.JUNGLE:  # En jungla el alcance no marca la fase de líneas.
            mine_ranged = my_stats.attack_range >= RANGED_MIN
            enemy_ranged = enemy_stats.attack_range >= RANGED_MIN
            range_diff = my_stats.attack_range - enemy_stats.attack_range
            if mine_ranged != enemy_ranged or abs(range_diff) >= RANGE_EDGE:
                weight = 0.5 if mine_ranged != enemy_ranged else 0.25
                score += weight if range_diff > 0 else -weight
                reasons.append(
                    f"Alcance {my_stats.attack_range:.0f} contra {enemy_stats.attack_range:.0f}: "
                    + ("puedes castigarle con ataques básicos cuando se acerque a los súbditos."
                       if range_diff > 0 else "puede castigarte con ataques básicos cuando te acerques a los súbditos.")
                )
        mine_ttk = _time_to_kill(my_stats, enemy_stats)
        enemy_ttk = _time_to_kill(enemy_stats, my_stats)
        if enemy_ttk >= mine_ttk * DUEL_MARGIN:
            score += 0.5
            reasons.append(f"Solo con ataques básicos a nivel 1 lo derrotarías en {mine_ttk:.0f} s y él a ti "
                           f"en {enemy_ttk:.0f} s (sin habilidades ni runas).")
        elif mine_ttk >= enemy_ttk * DUEL_MARGIN:
            score -= 0.5
            reasons.append(f"Solo con ataques básicos a nivel 1 te derrotaría en {enemy_ttk:.0f} s y tú a él "
                           f"en {mine_ttk:.0f} s (sin habilidades ni runas).")
    return PhaseEdge(levels="1-3", title="Primeros niveles", edge=_edge(score), reasons=reasons, kinds=kinds)


def _level_six(mine: ChampionProfile, enemy: ChampionProfile) -> PhaseEdge:
    score = 0.25 * (mine.early - enemy.early) + 0.25 * (mine.scaling - enemy.scaling)
    reasons = [f"Presión temprana y escalado según los perfiles: {mine.early} y {mine.scaling} contra "
               f"{enemy.early} y {enemy.scaling}."]
    if enemy.engage >= 2 and enemy.early >= 2:
        score -= 0.5
        reasons.append(f"{enemy.name} combina iniciación y presión temprana: con la definitiva puede buscar "
                       "una pelea completa. Vigila tu vida y tus hechizos de invocador.")
    if mine.engage >= 2 and mine.early >= 2:
        score += 0.5
        reasons.append("Tu campeón combina iniciación y presión temprana: el nivel 6 es una buena ventana "
                       "para buscar una pelea completa.")
    return PhaseEdge(levels="6", title="Definitiva", edge=_edge(score), reasons=reasons,
                     kinds=[EvidenceKind.INFERENCE])


def _mid_phase(mine: ChampionProfile, enemy: ChampionProfile) -> PhaseEdge:
    score = 0.25 * ((mine.early + mine.scaling) - (enemy.early + enemy.scaling))
    reasons = [f"Promedio de presión temprana y escalado: {(mine.early + mine.scaling) / 2:.1f} "
               f"contra {(enemy.early + enemy.scaling) / 2:.1f} (primeros objetos)."]
    return PhaseEdge(levels="7-10", title="Primeros objetos", edge=_edge(score), reasons=reasons,
                     kinds=[EvidenceKind.INFERENCE])


def _late_phase(mine: ChampionProfile, enemy: ChampionProfile, my_stats: BaseStats | None,
                enemy_stats: BaseStats | None) -> PhaseEdge:
    diff = mine.scaling - enemy.scaling
    reasons = [f"Escalado según los perfiles: {mine.scaling} contra {enemy.scaling}."]
    kinds = [EvidenceKind.INFERENCE]
    if my_stats and enemy_stats:
        my_hp, enemy_hp = my_stats.hp_at(16), enemy_stats.hp_at(16)
        if abs(my_hp - enemy_hp) >= 250:
            kinds.append(EvidenceKind.OFFICIAL)
            who = "Tú tendrás" if my_hp > enemy_hp else f"{enemy.name} tendrá"
            reasons.append(f"{who} más vida base a nivel 16 ({max(my_hp, enemy_hp):.0f} contra "
                           f"{min(my_hp, enemy_hp):.0f}), sin contar objetos.")
    return PhaseEdge(levels="11+", title="Fase tardía", edge=_edge(0.5 * diff), reasons=reasons, kinds=kinds)


def _phase_list(phases: list[PhaseEdge]) -> str:
    names = [f"{p.title.lower()} (nivel {p.levels})" for p in phases]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " y " + names[-1]


def _summary(enemy_name: str, phases: list[PhaseEdge]) -> str:
    wins = [p for p in phases if p.edge == 1]
    losses = [p for p in phases if p.edge == -1]
    if not wins and not losses:
        return "Enfrentamiento parejo en todas las fases según los datos disponibles."
    if wins and not losses:
        return f"La ventaja tiende a ser tuya en: {_phase_list(wins)}."
    if losses and not wins:
        return f"{enemy_name} tiende a tener ventaja en: {_phase_list(losses)}. Juega seguro y busca ayuda."
    if phases.index(losses[0]) < phases.index(wins[0]):
        return (f"{enemy_name} tiende a ganar antes, en {_phase_list(losses)}. Tu ventana llega en "
                f"{_phase_list(wins)}: evita peleas largas al principio y aguanta hasta tu momento.")
    return (f"Tu ventana es temprana, en {_phase_list(wins)}. En {_phase_list(losses)} la ventaja tiende a pasar "
            f"a {enemy_name}: aprovecha el principio para sacar ventaja.")


def _history(enemy: ChampionProfile, my_id: str, matches: list[MatchSummary], demo: bool,
             gold_at_10: dict[str, int]) -> Observation:
    against = [m for m in valid_matches(matches) if m.lane_opponent == enemy.id]
    if not against:
        return Observation(kind=EvidenceKind.INSUFFICIENT,
                           text=f"No tienes partidas descargadas contra {enemy.name} como rival directo.")
    wins = sum(1 for m in against if m.win)
    same = [m for m in against if m.champion_id == my_id]
    text = f"Contra {enemy.name}: {len(against)} partidas ({wins} V - {len(against) - wins} D)"
    if same:
        same_wins = sum(1 for m in same if m.win)
        text += f"; {len(same)} con este campeón ({same_wins} V)"
    diffs = [gold_at_10[m.match_id] for m in against if m.match_id in gold_at_10]
    if diffs:
        average = sum(diffs) / len(diffs)
        text += f". Diferencia media de oro al minuto 10: {average:+.0f} ({len(diffs)} con timeline)"
    text += ". Muestra pequeña: es una referencia, no una conclusión."
    if demo:
        text += " Son partidas FICTICIAS de demostración."
    return Observation(kind=EvidenceKind.OBSERVED, text=text, sample_size=len(against))


def analyze_matchup(mine: ChampionProfile, enemy: ChampionProfile, role: Role | None,
                    stats: dict[str, BaseStats], matches: list[MatchSummary], matches_are_demo: bool = False,
                    gold_at_10: dict[str, int] | None = None) -> LaneMatchup:
    """Ventaja probable por fases entre tu campeón y tu rival directo."""
    my_stats, enemy_stats = stats.get(mine.id), stats.get(enemy.id)
    phases = [
        _early_phase(mine, enemy, my_stats, enemy_stats, role),
        _level_six(mine, enemy),
        _mid_phase(mine, enemy),
        _late_phase(mine, enemy, my_stats, enemy_stats),
    ]
    durability = []
    if my_stats and enemy_stats:
        durability = [DurabilityRow(level=n, my_hp=my_stats.hp_at(n), enemy_hp=enemy_stats.hp_at(n),
                                    my_armor=my_stats.armor_at(n), enemy_armor=enemy_stats.armor_at(n))
                      for n in DURABILITY_LEVELS]
    return LaneMatchup(
        my_id=mine.id, enemy_id=enemy.id, role=role, phases=phases, summary=_summary(enemy.name, phases),
        durability=durability,
        history=_history(enemy, mine.id, matches, matches_are_demo, gold_at_10 or {}),
        estimated_profiles=ProfileOrigin.ESTIMATED in (mine.origin, enemy.origin),
    )


# --- Gankeos -----------------------------------------------------------------

GANK_LANES = {Role.TOP: (Role.TOP,), Role.MIDDLE: (Role.MIDDLE,), Role.BOTTOM: (Role.BOTTOM, Role.UTILITY)}


def gank_options(allies: dict[Role, ChampionProfile], enemies: dict[Role, ChampionProfile],
                 tags: dict[str, list[str]] | None = None) -> list[GankOption]:
    """Para un jungla: qué línea se presta más a un gankeo (inferencia a partir de perfiles).

    El perfil no mide la movilidad; la clase oficial «Assassin» se usa como
    pista de que el campeón suele tener habilidades para escapar."""
    tags = tags or {}
    options = []
    for lane, roles in GANK_LANES.items():
        targets = [enemies[r] for r in roles if r in enemies]
        if not targets:
            continue
        helpers = [allies[r] for r in roles if r in allies]
        score, reasons = 0.0, []
        assassins = [t for t in targets if "Assassin" in tags.get(t.id, [])]
        # En la línea inferior, el soporte puede proteger: cuenta el mejor de los dos.
        escape = min(3, max(t.disengage + (1 if t in assassins else 0) for t in targets))
        score += (1.5 - escape) * 0.6
        if assassins:
            reasons.append("Es asesino (clase oficial): suele tener movilidad para escapar.")
        if escape <= 1:
            reasons.append("Según su perfil, tiene poco desenganche: le cuesta escapar o protegerse de un gankeo.")
        elif escape >= 2 and not assassins:
            reasons.append("Tiene herramientas de desenganche: el gankeo puede fallar.")
        frontline = sum(t.frontline for t in targets) / len(targets)
        if frontline <= 1:
            score += 0.3
            reasons.append("Es frágil: un gankeo con control suele bastar para derribarlo.")
        elif frontline >= 2.5:
            score -= 0.4
            reasons.append("Aguanta mucho: aunque lo atrapes, puede sobrevivir.")
        if helpers:
            support = max(h.cc for h in helpers) + max(h.engage for h in helpers)
            if support >= 4:
                score += 0.6
                reasons.append("Tu aliado de la línea aporta control e iniciación para encadenar.")
            elif support <= 1:
                score -= 0.4
                reasons.append("Tu aliado de la línea aporta poco control: tendrás que hacerlo casi todo tú.")
            pressure = max(t.early for t in targets) - max(h.early for h in helpers)
            if pressure >= 1:
                score += 0.3
                reasons.append("El rival tiene más presión temprana que tu aliado: ayudarle evita que la "
                               "línea se pierda.")
        else:
            reasons.append("Aún no sabes quién es tu aliado de la línea.")
        verdict = "Buen objetivo" if score >= GOOD_GANK else "Posible" if score >= 0 else "Difícil"
        options.append(GankOption(lane=lane, enemy_ids=[t.id for t in targets], score=round(score, 2),
                                  verdict=verdict, reasons=reasons))
    return sorted(options, key=lambda o: o.score, reverse=True)


def gank_danger(mine: ChampionProfile | None, jungler: ChampionProfile) -> GankDanger:
    """Para quien juega en una línea: cuánto puede castigarle el jungla rival."""
    danger = jungler.early + jungler.engage + 0.5 * jungler.cc - (mine.disengage if mine else 0)
    reasons = [f"Presión temprana {jungler.early}, iniciación {jungler.engage} y control {jungler.cc} "
               f"de {jungler.name} según su perfil."]
    if mine:
        reasons.append(f"Tu desenganche: {mine.disengage}.")
    level = "alto" if danger >= 4.5 else "medio" if danger >= 3 else "bajo"
    if level == "alto":
        reasons.append("Si no sabes dónde está, juega cerca de tu torre y deja visión en el río.")
    return GankDanger(jungler_id=jungler.id, level=level, reasons=reasons)
