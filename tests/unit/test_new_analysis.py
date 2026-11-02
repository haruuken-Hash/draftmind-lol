"""Puntuación de rendimiento, fase de líneas, estadísticas por campeón y bloqueos."""

from datetime import datetime, timedelta, timezone

import pytest

from draftmind.analysis.ban_analyzer import suggest_bans
from draftmind.analysis.champion_stats import champion_performance, comfort_pool, recent_form, role_distribution
from draftmind.analysis.lane_analyzer import analyze_lane, lane_trend, players_from_match
from draftmind.analysis.performance import ParticipantLine, score_match
from draftmind.domain.enums import EvidenceKind, Role
from draftmind.domain.models import MatchSummary

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


# --- Puntuación de rendimiento ------------------------------------------------------

def line(key, team, win, role=Role.TOP, k=2, d=2, a=2, dmg=10000, gold=8000, cs=150, vision=15):
    return ParticipantLine(key=key, team_id=team, win=win, role=role, kills=k, deaths=d, assists=a,
                           damage=dmg, gold=gold, cs=cs, vision=vision)


def test_best_player_gets_top_score_and_badges():
    lines = [line(f"w{i}", 100, True) for i in range(5)] + [line(f"l{i}", 200, False) for i in range(5)]
    lines[0] = line("star", 100, True, k=12, d=1, a=8, dmg=30000, gold=14000, cs=220, vision=30)
    lines[5] = line("ace", 200, False, k=6, d=3, a=4, dmg=20000, gold=11000, cs=190, vision=25)
    result = score_match(lines, minutes=30)
    assert result["star"].rank == 1 and result["star"].badge == "MVP" and result["star"].score > 8
    assert result["ace"].badge == "ACE"
    assert all(0 <= r.score <= 10 for r in result.values())
    assert sum(1 for r in result.values() if r.badge) == 2


def test_supports_are_not_penalised_for_cs():
    lines = [line(f"p{i}", 100 if i < 5 else 200, i < 5) for i in range(10)]
    support = line("sup", 100, True, role=Role.UTILITY, cs=20)
    carry = line("adc", 100, True, role=Role.BOTTOM, cs=20)
    with_support = score_match(lines[:9] + [support], 30)["sup"].score
    with_carry = score_match(lines[:9] + [carry], 30)["adc"].score
    assert with_support > with_carry


def test_empty_or_invalid_input():
    assert score_match([], 30) == {}
    assert score_match([line("a", 100, True), line("b", 200, False)], 0) == {}


# --- Fase de líneas ----------------------------------------------------------------------

def frame(minute, me_gold, opp_gold, me_cs=0, me_jungle=0, opp_cs=0, events=()):
    pf = {str(i): {"totalGold": 500, "xp": 0, "minionsKilled": 0, "jungleMinionsKilled": 0} for i in range(1, 11)}
    pf["2"] = {"totalGold": me_gold, "xp": minute * 400, "minionsKilled": me_cs, "jungleMinionsKilled": me_jungle}
    pf["7"] = {"totalGold": opp_gold, "xp": minute * 380, "minionsKilled": opp_cs, "jungleMinionsKilled": 0}
    return {"timestamp": minute * 60000, "participantFrames": pf, "events": list(events)}


def timeline():
    frames = [frame(m, 500 + m * 300, 500 + m * 350) for m in range(18)]
    frames[10] = frame(10, 3400, 3900, me_jungle=58, opp_cs=66)
    frames[15] = frame(15, 5600, 5700, me_jungle=92, opp_cs=95)
    frames[4]["events"] = [{"type": "CHAMPION_KILL", "timestamp": 4 * 60000 + 5000, "killerId": 1,
                            "victimId": 6, "assistingParticipantIds": [2]}]
    frames[8]["events"] = [{"type": "ELITE_MONSTER_KILL", "timestamp": 8 * 60000, "killerTeamId": 100,
                            "monsterType": "DRAGON"},
                           {"type": "CHAMPION_KILL", "timestamp": 8 * 60000 + 1, "killerId": 7, "victimId": 2,
                            "assistingParticipantIds": []}]
    frames[16]["events"] = [{"type": "CHAMPION_KILL", "timestamp": 16 * 60000, "killerId": 2, "victimId": 9}]
    return {"info": {"frameInterval": 60000, "frames": frames,
                     "participants": [{"participantId": i, "puuid": f"p{i}"} for i in range(1, 11)]}}


RAW_MATCH = {"info": {"participants": [
    {"participantId": i, "teamId": 100 if i <= 5 else 200,
     "teamPosition": ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"][(i - 1) % 5]} for i in range(1, 11)]}}


def jungle_match(match_id="M1"):
    return MatchSummary(match_id=match_id, platform="LA1", puuid="p2", champion_id="Kayn", role=Role.JUNGLE,
                        participant_id=2, opponent_participant_id=7, played_at=NOW)


def test_lane_snapshots_and_events():
    a = analyze_lane(timeline(), jungle_match(), players_from_match(RAW_MATCH))
    s10 = next(s for s in a.snapshots if s.minute == 10)
    assert (s10.gold_diff, s10.jungle_cs, s10.cs_diff) == (-500, 58, -8)
    assert [s.minute for s in a.snapshots] == [5, 10, 15]
    assert a.first_takedown_minute == 4 and a.first_takedown_lane is Role.TOP  # Víctima: jugador 6 (TOP rival).
    assert a.deaths_before_15 == 1 and a.takedowns_before_15 == 1  # El asesinato del minuto 16 no cuenta.
    assert a.objectives_before_15["aliado"] == {"dragones": 1}
    text = " ".join(o.text for o in a.observations)
    assert "-500 de oro" in text and "recuperaste terreno" in text and "minuto 4" in text


def test_lane_without_participant_id():
    match = jungle_match().model_copy(update={"participant_id": None})
    assert analyze_lane(timeline(), match, players_from_match(RAW_MATCH)) is None


def test_lane_trend_needs_three_games():
    analyses = [analyze_lane(timeline(), jungle_match(str(i)), players_from_match(RAW_MATCH)) for i in range(3)]
    trend = lane_trend(analyses)
    assert trend.sample_size == 3 and "-500 de oro" in trend.text
    assert lane_trend(analyses[:2]) is None


# --- Estadísticas por campeón ---------------------------------------------------------

def game(i, champ="Kayn", role=Role.JUNGLE, win=True, opp="Nocturne", score=6.0):
    return MatchSummary(match_id=str(i), platform="LA1", puuid="P", champion_id=champ, role=role, win=win,
                        kills=5, deaths=2, assists=5, cs=180, duration_s=1800, team_kills=20,
                        lane_opponent=opp, performance_score=score, played_at=NOW - timedelta(days=i))


def test_champion_performance_and_pool():
    matches = [game(0), game(1, win=False), game(2, champ="Lillia"), game(3, champ="Garen", role=Role.TOP)]
    perf = champion_performance(matches)
    assert perf[0].champion_id == "Kayn" and perf[0].games == 2 and perf[0].win_rate == 0.5
    assert perf[0].kda == 5.0 and perf[0].avg_score == 6.0
    assert role_distribution(matches)[Role.JUNGLE] == 3
    assert comfort_pool(matches, Role.JUNGLE, []) == ["Kayn", "Lillia"]
    assert comfort_pool([], Role.JUNGLE, ["Ahri"]) == ["Ahri"]  # Sin partidas: maestría.
    assert recent_form(matches) == [True, False, True, True]


# --- Bloqueos ------------------------------------------------------------------------------

def test_ban_suggestions_from_personal_losses(dataset):
    profiles = {p.id: p for p in dataset.champions}
    matches = [game(i, opp="LeeSin", win=False) for i in range(3)] + [game(9, opp="Amumu", win=True),
                                                                      game(10, opp="Amumu", win=True)]
    bans = suggest_bans(Role.JUNGLE, ["MasterYi"], matches, profiles)
    top = bans[0]
    assert top.champion_id == "LeeSin" and top.games == 3
    assert EvidenceKind.OBSERVED in top.kinds and "3 de 3" in top.reasons[0]
    assert "Amumu" not in [b.champion_id for b in bans if EvidenceKind.OBSERVED in b.kinds]


def test_ban_suggestions_from_profiles_respect_role_and_exclusions(dataset):
    profiles = {p.id: p for p in dataset.champions}
    bans = suggest_bans(Role.TOP, ["Kayle"], [], profiles, exclude={"Renekton"})
    ids = [b.champion_id for b in bans]
    assert ids and "Renekton" not in ids and "Kayle" not in ids
    assert all(Role.TOP in profiles[i].roles for i in ids)
    assert all(b.kinds == [EvidenceKind.INFERENCE] for b in bans)


def test_no_data_no_suggestions(dataset):
    assert suggest_bans(Role.TOP, [], [], {p.id: p for p in dataset.champions}) == []
