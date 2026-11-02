"""Conversión de una partida de match-v5 (JSON) a ``MatchSummary``.

Significado de los campos según el esquema oficial de match-v5:
- info.gameDuration: antes del parche 11.20 en MILISEGUNDOS; después en
  segundos. Riot indica que, si existe info.gameEndTimestamp, son segundos.
- championName: recomendado frente a championId para partidas antiguas.
  Coincide con el identificador de Data Dragon (p. ej. "MonkeyKing").
- gameVersion: las dos primeras partes indican el parche.
- teamPosition: TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY o vacío si no se pudo
  determinar.
- totalMinionsKilled (súbditos) + neutralMinionsKilled (monstruos) = CS.
"""

from datetime import datetime, timezone
from typing import Any

from draftmind.analysis.performance import ParticipantLine, score_match
from draftmind.domain.enums import Role
from draftmind.domain.models import MatchSummary


def _int(data: dict, key: str) -> int | None:
    value = data.get(key)
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _role(value: Any) -> Role | None:
    try:
        return Role(value)
    except ValueError:
        return None


_PERFORMANCE_FIELDS = ("kills", "deaths", "assists", "totalDamageDealtToChampions", "goldEarned",
                       "totalMinionsKilled", "neutralMinionsKilled", "visionScore")


def _performance(participants: list, duration: int | None) -> dict:
    """Puntuación de los 10 jugadores; vacía si falta algún dato."""
    if len(participants) != 10 or not duration:
        return {}
    lines = []
    for p in participants:
        values = [_int(p, k) for k in _PERFORMANCE_FIELDS]
        if None in values or not isinstance(p.get("win"), bool) or p.get("teamId") is None or not p.get("puuid"):
            return {}
        kills, deaths, assists, damage, gold, minions, monsters, vision = values
        lines.append(ParticipantLine(
            key=p["puuid"], team_id=p["teamId"], win=p["win"], role=_role(p.get("teamPosition")),
            kills=kills, deaths=deaths, assists=assists, damage=damage, gold=gold,
            cs=minions + monsters, vision=vision,
        ))
    return score_match(lines, duration / 60)


def summarize_match(raw: dict, puuid: str, platform: str, is_demo: bool = False) -> MatchSummary | None:
    """Devuelve None si la partida no contiene al jugador o está incompleta."""
    info = raw.get("info") or {}
    participants = info.get("participants") or []
    me = next((p for p in participants if p.get("puuid") == puuid), None)
    match_id = (raw.get("metadata") or {}).get("matchId")
    if me is None or not match_id or not me.get("championName"):
        return None

    duration = _int(info, "gameDuration")
    if duration is not None and "gameEndTimestamp" not in info:
        duration //= 1000  # Formato anterior al parche 11.20 (milisegundos).

    created = _int(info, "gameCreation")
    version = info.get("gameVersion")
    patch = ".".join(version.split(".")[:2]) if isinstance(version, str) and version.count(".") >= 1 else None

    minions, monsters = _int(me, "totalMinionsKilled"), _int(me, "neutralMinionsKilled")
    cs = minions + monsters if minions is not None and monsters is not None else None

    team_id = me.get("teamId")
    teammates = [p for p in participants if p.get("teamId") == team_id]
    rivals = [p for p in participants if p.get("teamId") != team_id]
    team_kills_values = [_int(p, "kills") for p in teammates]
    team_kills = sum(team_kills_values) if all(v is not None for v in team_kills_values) else None

    role = _role(me.get("teamPosition"))
    opponent = next((p for p in rivals if role and p.get("teamPosition") == role.value), None)

    keystone = None
    styles = (me.get("perks") or {}).get("styles") or []
    # El esquema documenta "description" como texto libre; si no aparece
    # "primaryStyle", se toma el primer árbol de la lista.
    primary = next((s for s in styles if s.get("description") == "primaryStyle"), styles[0] if styles else None)
    if primary and primary.get("selections"):
        keystone = primary["selections"][0].get("perk")

    performance = _performance(participants, duration).get(puuid)

    return MatchSummary(
        match_id=match_id,
        participant_id=_int(me, "participantId"),
        opponent_participant_id=_int(opponent, "participantId") if opponent else None,
        performance_score=performance.score if performance else None,
        performance_rank=performance.rank if performance else None,
        badge=performance.badge if performance else None,
        platform=platform,
        puuid=puuid,
        is_demo=is_demo,
        queue_id=_int(info, "queueId"),
        played_at=datetime.fromtimestamp(created / 1000, timezone.utc) if created else None,
        duration_s=duration,
        patch=patch,
        champion_id=me["championName"],
        role=role,
        win=me.get("win") if isinstance(me.get("win"), bool) else None,
        kills=_int(me, "kills"),
        deaths=_int(me, "deaths"),
        assists=_int(me, "assists"),
        cs=cs,
        gold=_int(me, "goldEarned"),
        vision_score=_int(me, "visionScore"),
        damage_to_champions=_int(me, "totalDamageDealtToChampions"),
        damage_taken=_int(me, "totalDamageTaken"),
        team_kills=team_kills,
        items=[v for k in range(7) if (v := _int(me, f"item{k}"))],
        summoner_spells=[v for k in ("summoner1Id", "summoner2Id") if (v := _int(me, k))],
        keystone_id=keystone,
        allies=[p["championName"] for p in teammates if p is not me and p.get("championName")],
        enemies=[p["championName"] for p in rivals if p.get("championName")],
        lane_opponent=opponent.get("championName") if opponent else None,
    )
