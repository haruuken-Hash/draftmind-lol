from datetime import datetime, timedelta, timezone

import pytest

from draftmind.analysis.postgame_analyzer import (
    MatchFilter,
    averages,
    cs_per_min,
    is_probable_remake,
    kda,
    kill_participation,
    observations,
)
from draftmind.data.database import create_db_engine, init_database
from draftmind.data.repositories.match_repository import MatchRepository
from draftmind.domain.enums import EvidenceKind, Role
from draftmind.domain.models import MatchSummary
from draftmind.integrations.riot_match import summarize_match
from draftmind.services.match_service import MatchService

NOW = datetime(2026, 10, 28, tzinfo=timezone.utc)


def match(**kw) -> MatchSummary:
    base = dict(match_id="X", platform="LA1", puuid="P", champion_id="Ahri", role=Role.MIDDLE,
                win=True, kills=5, deaths=2, assists=7, cs=180, duration_s=1800, team_kills=20,
                vision_score=20, played_at=NOW)
    base.update(kw)
    return MatchSummary(**base)


def raw_match(**info_overrides):
    me = {"puuid": "P", "championName": "MonkeyKing", "teamId": 100, "teamPosition": "TOP", "win": True,
          "kills": 4, "deaths": 0, "assists": 6, "totalMinionsKilled": 150, "neutralMinionsKilled": 10,
          "goldEarned": 9000, "visionScore": 15, "totalDamageDealtToChampions": 15000,
          "totalDamageTaken": 20000, "item0": 3047, "item1": 0, "item6": 3340,
          "summoner1Id": 4, "summoner2Id": 12,
          "perks": {"styles": [{"description": "primaryStyle", "style": 8400, "selections": [{"perk": 8437}]}]}}
    ally = {"puuid": "A", "championName": "Ahri", "teamId": 100, "teamPosition": "MIDDLE", "kills": 6}
    enemy = {"puuid": "E", "championName": "Darius", "teamId": 200, "teamPosition": "TOP", "kills": 3}
    info = {"gameCreation": 1_790_000_000_000, "gameDuration": 1500, "gameEndTimestamp": 1,
            "gameVersion": "16.21.712.5555", "queueId": 420, "participants": [me, ally, enemy]}
    info.update(info_overrides)
    return {"metadata": {"matchId": "LA1_123"}, "info": info}


# --- Lectura de match-v5 ---------------------------------------------------------

def test_summarize_match_fields():
    m = summarize_match(raw_match(), "P", "LA1")
    assert m.champion_id == "MonkeyKing" and m.role is Role.TOP
    assert m.cs == 160 and m.duration_s == 1500 and m.patch == "16.21"
    assert m.team_kills == 10  # 4 propios + 6 del aliado.
    assert m.items == [3047, 3340]  # Los huecos vacíos (0) se descartan.
    assert m.keystone_id == 8437 and m.summoner_spells == [4, 12]
    assert m.lane_opponent == "Darius" and m.allies == ["Ahri"] and m.enemies == ["Darius"]


def test_old_matches_duration_in_milliseconds():
    raw = raw_match(gameDuration=1_500_000)
    del raw["info"]["gameEndTimestamp"]
    assert summarize_match(raw, "P", "LA1").duration_s == 1500


def test_incomplete_match_keeps_missing_fields_as_none():
    raw = raw_match()
    me = raw["info"]["participants"][0]
    for key in ("totalMinionsKilled", "visionScore", "win"):
        del me[key]
    m = summarize_match(raw, "P", "LA1")
    assert m.cs is None and m.vision_score is None and m.win is None
    assert cs_per_min(m) is None


def test_match_without_player_is_skipped():
    assert summarize_match(raw_match(), "OTRO", "LA1") is None
    assert summarize_match({"info": {}}, "P", "LA1") is None


# --- Métricas ----------------------------------------------------------------------

def test_kda_and_zero_deaths():
    assert kda(match(kills=5, deaths=2, assists=7)) == 6.0
    assert kda(match(kills=3, deaths=0, assists=4)) == 7.0
    assert kda(match(kills=None)) is None


def test_cs_per_min():
    assert cs_per_min(match(cs=180, duration_s=1800)) == pytest.approx(6.0)
    assert cs_per_min(match(duration_s=0)) is None


def test_kill_participation():
    assert kill_participation(match(kills=5, assists=5, team_kills=20)) == 0.5
    assert kill_participation(match(team_kills=0)) is None


def test_remakes_are_excluded_from_averages():
    remake = match(duration_s=200, kills=0, deaths=0, assists=0)
    assert is_probable_remake(remake)
    assert averages([remake, match()])["kda"] == 6.0


def test_filters():
    games = [
        match(match_id="1", champion_id="Ahri", win=True, played_at=NOW - timedelta(days=1)),
        match(match_id="2", champion_id="Garen", role=Role.TOP, win=False, played_at=NOW - timedelta(days=20)),
    ]
    assert [m.match_id for m in MatchFilter(champion_id="Garen").apply(games, NOW)] == ["2"]
    assert [m.match_id for m in MatchFilter(role=Role.MIDDLE).apply(games, NOW)] == ["1"]
    assert [m.match_id for m in MatchFilter(days=7).apply(games, NOW)] == ["1"]
    assert [m.match_id for m in MatchFilter(win=False).apply(games, NOW)] == ["2"]


# --- Observaciones -------------------------------------------------------------------

def test_observations_need_enough_data():
    obs = observations([match()])
    assert any(o.kind is EvidenceKind.INSUFFICIENT for o in obs)


def test_trend_detects_cs_improvement_with_sample_size():
    games = [match(match_id=str(i), cs=240 if i < 5 else 160, played_at=NOW - timedelta(days=i))
             for i in range(10)]
    obs = observations(games)
    cs_obs = next(o for o in obs if "CS por minuto" in o.text)
    assert "ha mejorado" in cs_obs.text and cs_obs.sample_size == 10
    assert cs_obs.kind is EvidenceKind.OBSERVED
    texts = " ".join(o.text for o in obs).lower()
    assert "mala decisión" not in texts and "error" not in texts


def test_empty_observations():
    assert observations([])[0].kind is EvidenceKind.INSUFFICIENT


# --- Servicio y caché ------------------------------------------------------------------

class FakeRiot:
    def __init__(self):
        self.calls = []

    def account_by_riot_id(self, platform, name, tag):
        self.calls.append("account")
        return {"puuid": "P", "gameName": name, "tagLine": tag}

    def match_ids(self, platform, puuid, count=20, queue=None):
        self.calls.append("ids")
        return ["LA1_123"]

    def match(self, platform, match_id):
        self.calls.append(match_id)
        return raw_match()


class LaterRiot(FakeRiot):
    """La primera consulta solo ve una partida vieja; después aparece la recién terminada."""

    def __init__(self):
        super().__init__()
        self.published = ["LA1_100"]
        self.timeline_error = True

    def match_ids(self, platform, puuid, count=20, queue=None):
        return list(reversed(self.published))  # La API devuelve primero la más reciente.

    def match(self, platform, match_id):
        created = 1_790_000_000_000 + int(match_id.split("_")[1]) * 1000
        raw = raw_match(gameCreation=created)
        raw["metadata"]["matchId"] = match_id
        return raw

    def match_timeline(self, platform, match_id):
        from draftmind.integrations.riot_api import RiotApiError

        raise RiotApiError("timeline no disponible")


def test_fetch_latest_waits_until_the_new_match_is_published():
    from draftmind.integrations.riot_api import Platform

    service = MatchService(MatchRepository(init_database(create_db_engine(None))), LaterRiot())
    account = service.link_account(Platform.LA1, "Ana", "LAN")
    service.fetch_recent(account)                     # Ya tenía guardada LA1_100.
    _, newest = service.fetch_latest(account)
    assert newest is None                             # Riot aún no publica la nueva.
    service.client.published.append("LA1_200")
    matches, newest = service.fetch_latest(account)
    assert newest.match_id == "LA1_200"               # Un fallo del timeline no impide el análisis.
    assert [m.match_id for m in matches] == ["LA1_200", "LA1_100"]


class KeyChangeRiot(FakeRiot):
    """Riot cifra el PUUID para cada aplicación: con otra clave cambia y el viejo da 400."""

    def __init__(self):
        super().__init__()
        self.puuid = "P"

    def account_by_riot_id(self, platform, name, tag):
        self.calls.append("account")
        return {"puuid": self.puuid, "gameName": name, "tagLine": tag}

    def match_ids(self, platform, puuid, count=20, queue=None):
        from draftmind.integrations.riot_api import RiotBadRequest

        if puuid != self.puuid:
            raise RiotBadRequest("400")
        return ["LA1_123"]

    def match(self, platform, match_id):
        self.calls.append(match_id)
        raw = raw_match()
        raw["info"]["participants"][0]["puuid"] = self.puuid
        raw["metadata"]["participants"] = [self.puuid, "A", "E"]
        return raw


def test_new_application_key_updates_puuid_and_stored_matches():
    from draftmind.integrations.riot_api import Platform

    repo = MatchRepository(init_database(create_db_engine(None)))
    riot = KeyChangeRiot()
    service = MatchService(repo, riot)
    old = service.link_account(Platform.LA1, "Ana", "LAN")
    assert len(service.fetch_recent(old)[0]) == 1

    riot.puuid = "P2"                                 # Clave de otra aplicación.
    matches, new = service.fetch_recent(old)          # La interfaz aún tiene la cuenta vieja.
    assert repo.get_account().puuid == "P2"
    assert len(matches) == 1 and new == 0             # Las partidas guardadas siguen siendo tuyas.
    assert riot.calls.count("LA1_123") == 2           # Se volvió a descargar con el PUUID nuevo.
    assert service.link_account(Platform.LA1, "Ana", "LAN").puuid == "P2"


def test_service_caches_account_and_matches():
    from draftmind.integrations.riot_api import Platform

    repo = MatchRepository(init_database(create_db_engine(None)))
    riot = FakeRiot()
    service = MatchService(repo, riot)
    account = service.link_account(Platform.LA1, "Ana", "LAN")
    service.link_account(Platform.LA1, "ana", "lan")  # Mismo Riot ID: no repite la petición.
    matches, new = service.fetch_recent(account)
    _, new_again = service.fetch_recent(account)
    assert riot.calls.count("account") == 1
    assert riot.calls.count("LA1_123") == 1  # La partida guardada no se vuelve a pedir.
    assert (new, new_again) == (1, 0)
    assert matches[0].champion_id == "MonkeyKing"


def test_service_without_key_cannot_fetch():
    from draftmind.integrations.riot_api import Platform

    service = MatchService(MatchRepository(init_database(create_db_engine(None))), None)
    assert not service.can_use_api
    with pytest.raises(RuntimeError):
        service.link_account(Platform.LA1, "Ana", "LAN")


def test_demo_matches_are_flagged():
    account, matches = MatchService.demo_matches()
    assert account.riot_id == "Jugador Demo#DEMO"
    assert len(matches) == 14 and all(m.is_demo for m in matches)
    assert matches[0].played_at > matches[-1].played_at  # Más recientes primero.
