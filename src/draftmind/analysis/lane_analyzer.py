"""Fase de líneas a partir del timeline de match-v5.

Estructura comprobada con una partida real (01/11/2026):
- info.frameInterval = 60000: una «foto» por minuto en info.frames[n].
- frames[n].participantFrames["1".."10"]: totalGold, xp, level,
  minionsKilled, jungleMinionsKilled...
- frames[n].events: CHAMPION_KILL (killerId, victimId,
  assistingParticipantIds), ELITE_MONSTER_KILL (killerTeamId, monsterType)...
- info.participants: participantId <-> puuid.

Solo hay una foto por minuto: no se pueden reconstruir rutas ni decisiones,
y el análisis no lo intenta.
"""

from pydantic import BaseModel, Field

from draftmind.domain.enums import EvidenceKind, Role
from draftmind.domain.models import MatchSummary, Observation

CHECKPOINTS = (5, 10, 15)
EARLY_MINUTES = 15
MONSTER_LABELS = {"DRAGON": "dragones", "RIFTHERALD": "Heraldo", "HORDE": "larvas del Vacío",
                  "BARON_NASHOR": "Barón", "ATAKHAN": "Atakhan"}


class LaneSnapshot(BaseModel):
    minute: int
    gold: int
    opponent_gold: int | None = None
    cs: int                     # Súbditos + monstruos.
    opponent_cs: int | None = None
    jungle_cs: int
    xp: int
    opponent_xp: int | None = None

    @property
    def gold_diff(self) -> int | None:
        return None if self.opponent_gold is None else self.gold - self.opponent_gold

    @property
    def cs_diff(self) -> int | None:
        return None if self.opponent_cs is None else self.cs - self.opponent_cs

    @property
    def xp_diff(self) -> int | None:
        return None if self.opponent_xp is None else self.xp - self.opponent_xp


class LaneAnalysis(BaseModel):
    match_id: str
    role: Role | None
    snapshots: list[LaneSnapshot]
    first_takedown_minute: int | None = None     # Primer asesinato o asistencia.
    first_takedown_lane: Role | None = None      # Posición de la víctima.
    deaths_before_15: int = 0
    takedowns_before_15: int = 0
    objectives_before_15: dict[str, dict[str, int]] = Field(default_factory=dict)  # "aliado"/"rival" -> tipo -> n
    observations: list[Observation] = Field(default_factory=list)


def _frame_value(frame: dict, pid: int | None, key: str) -> int | None:
    if pid is None:
        return None
    value = (frame.get("participantFrames") or {}).get(str(pid), {}).get(key)
    return value if isinstance(value, int) else None


def players_from_match(raw_match: dict) -> dict[int, tuple[int | None, Role | None]]:
    """participantId -> (teamId, posición), leído de la partida (no se supone el orden)."""
    players = {}
    for p in (raw_match.get("info") or {}).get("participants") or []:
        pid = p.get("participantId")
        if isinstance(pid, int):
            try:
                role = Role(p.get("teamPosition"))
            except ValueError:
                role = None
            players[pid] = (p.get("teamId"), role)
    return players


def analyze_lane(timeline: dict, match: MatchSummary,
                 players: dict[int, tuple[int | None, Role | None]]) -> LaneAnalysis | None:
    info = timeline.get("info") or {}
    frames = info.get("frames") or []
    me, opp = match.participant_id, match.opponent_participant_id
    if me is None or not frames or me not in players:
        return None
    my_team = players[me][0]
    roles_by_pid = {pid: role for pid, (_, role) in players.items()}

    snapshots = []
    for minute in CHECKPOINTS:
        if minute >= len(frames):
            break
        frame = frames[minute]
        gold, xp = _frame_value(frame, me, "totalGold"), _frame_value(frame, me, "xp")
        minions, monsters = _frame_value(frame, me, "minionsKilled"), _frame_value(frame, me, "jungleMinionsKilled")
        if None in (gold, xp, minions, monsters):
            continue
        opp_minions, opp_monsters = _frame_value(frame, opp, "minionsKilled"), _frame_value(frame, opp, "jungleMinionsKilled")
        snapshots.append(LaneSnapshot(
            minute=minute, gold=gold, xp=xp, cs=minions + monsters, jungle_cs=monsters,
            opponent_gold=_frame_value(frame, opp, "totalGold"),
            opponent_xp=_frame_value(frame, opp, "xp"),
            opponent_cs=(opp_minions + opp_monsters) if None not in (opp_minions, opp_monsters) else None,
        ))

    analysis = LaneAnalysis(match_id=match.match_id, role=match.role, snapshots=snapshots)
    objectives: dict[str, dict[str, int]] = {"aliado": {}, "rival": {}}
    for frame in frames:
        for event in frame.get("events") or []:
            minute = (event.get("timestamp") or 0) // 60000
            if minute >= EARLY_MINUTES:
                continue
            if event.get("type") == "CHAMPION_KILL":
                involved = event.get("killerId") == me or me in (event.get("assistingParticipantIds") or [])
                if involved:
                    analysis.takedowns_before_15 += 1
                    if analysis.first_takedown_minute is None:
                        analysis.first_takedown_minute = minute
                        analysis.first_takedown_lane = roles_by_pid.get(event.get("victimId"))
                if event.get("victimId") == me:
                    analysis.deaths_before_15 += 1
            elif event.get("type") == "ELITE_MONSTER_KILL":
                side = "aliado" if event.get("killerTeamId") == my_team else "rival"
                label = MONSTER_LABELS.get(event.get("monsterType"), str(event.get("monsterType")).lower())
                objectives[side][label] = objectives[side].get(label, 0) + 1
    analysis.objectives_before_15 = objectives
    analysis.observations = _observations(analysis)
    return analysis


def _observations(a: LaneAnalysis) -> list[Observation]:
    out: list[Observation] = []
    by_minute = {s.minute: s for s in a.snapshots}
    s10, s15 = by_minute.get(10), by_minute.get(15)
    if s10 and s10.gold_diff is not None:
        trend = ""
        if s15 and s15.gold_diff is not None:
            change = s15.gold_diff - s10.gold_diff
            trend = (" y la ventaja creció" if change > 300 else " y la diferencia se redujo" if change < -300 else "")
            trend = trend if s10.gold_diff >= 0 else (" y recuperaste terreno" if change > 300 else
                                                      " y la desventaja aumentó" if change < -300 else "")
            trend += f" ({s15.gold_diff:+} de oro al minuto 15)"
        out.append(Observation(kind=EvidenceKind.OBSERVED,
                               text=f"Al minuto 10 tenías {s10.gold_diff:+} de oro frente a tu rival directo{trend}."))
    if a.role is Role.JUNGLE and s10:
        out.append(Observation(kind=EvidenceKind.OBSERVED,
                               text=f"Monstruos de jungla al minuto 10: {s10.jungle_cs}"
                                    + (f" (CS total del rival: {s10.opponent_cs})." if s10.opponent_cs is not None else ".")))
    if a.first_takedown_minute is not None:
        lane = f" en la posición {a.first_takedown_lane.label}" if a.first_takedown_lane else ""
        out.append(Observation(kind=EvidenceKind.OBSERVED,
                               text=f"Tu primera participación en un asesinato fue en el minuto "
                                    f"{a.first_takedown_minute}{lane}."))
    elif a.snapshots:
        out.append(Observation(kind=EvidenceKind.OBSERVED,
                               text="No participaste en ningún asesinato antes del minuto 15."))
    if a.deaths_before_15:
        out.append(Observation(kind=EvidenceKind.EDUCATIONAL,
                               text=f"Moriste {a.deaths_before_15} {'vez' if a.deaths_before_15 == 1 else 'veces'} "
                                    "antes del minuto 15. En la repetición, ¿tenías visión o información de dónde "
                                    "estaba el jungla rival?"))
    out.append(Observation(kind=EvidenceKind.EDUCATIONAL,
                           text="El timeline tiene una foto por minuto: describe el resultado, no las decisiones. "
                                "Para entender el porqué, revisa la repetición."))
    return out


def lane_trend(analyses: list[LaneAnalysis], minute: int = 10) -> Observation | None:
    """Media de diferencia de oro y CS a un minuto dado entre varias partidas."""
    values = [s for a in analyses for s in a.snapshots if s.minute == minute and s.gold_diff is not None]
    if len(values) < 3:
        return None
    gold = sum(s.gold_diff for s in values) / len(values)
    cs = [s.cs_diff for s in values if s.cs_diff is not None]
    cs_text = f" y {sum(cs) / len(cs):+.1f} de CS" if cs else ""
    return Observation(kind=EvidenceKind.OBSERVED, sample_size=len(values),
                       text=f"En {len(values)} partidas analizadas llegas al minuto {minute} con {gold:+.0f} de oro"
                            f"{cs_text} de media frente a tu rival directo.")
