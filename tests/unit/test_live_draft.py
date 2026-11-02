"""Draft en vivo: lockfile, cliente local (simulado), sesión y servicio."""

import base64
import json
import ssl
from pathlib import Path

import httpx
import pytest

from draftmind.domain.enums import Role
from draftmind.integrations.champ_select import parse_session
from draftmind.integrations.league_client import (
    ALLOWED_PATHS,
    RIOT_ROOT_CERT,
    LeagueClient,
    LeagueClientError,
    Lockfile,
    read_lockfile,
)
from draftmind.services.live_draft_service import LiveDraftService, LiveState

SESSION = json.loads((Path(__file__).parents[1] / "fixtures" / "champ_select_session.json").read_text(encoding="utf-8"))
# Claves reales de Data Dragon (champion.json, campo "key").
KEYS = {54: "Malphite", 32: "Amumu", 103: "Ahri", 222: "Jinx", 122: "Darius", 64: "LeeSin",
        238: "Zed", 89: "Leona", 157: "Yasuo"}
LOCK = Lockfile(process="LeagueClient", pid=1, port=50000, password="clave-local", protocol="https")


# --- Lockfile -------------------------------------------------------------------

def test_read_lockfile(tmp_path):
    (tmp_path / "lockfile").write_text("LeagueClient:1234:54321:abcDEF123:https", encoding="utf-8")
    lock = read_lockfile(tmp_path)
    assert (lock.pid, lock.port, lock.protocol, lock.password) == (1234, 54321, "https", "abcDEF123")
    assert "abcDEF123" not in repr(lock)  # La contraseña no aparece al imprimirlo.


def test_missing_lockfile_means_client_closed(tmp_path):
    assert read_lockfile(tmp_path) is None


@pytest.mark.parametrize("content", ["", "a:b:c", "LeagueClient:x:54321:pw:https", "L:1:2:pw:ftp"])
def test_malformed_lockfile(tmp_path, content):
    (tmp_path / "lockfile").write_text(content, encoding="utf-8")
    with pytest.raises(LeagueClientError):
        read_lockfile(tmp_path)


# --- Cliente local ------------------------------------------------------------------

def make_client(handler):
    return LeagueClient(LOCK, http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_client_uses_localhost_basic_auth_and_get_only():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json="ChampSelect")

    assert make_client(handler).gameflow_phase() == "ChampSelect"
    request = seen[0]
    assert request.method == "GET"
    assert str(request.url) == "https://127.0.0.1:50000/lol-gameflow/v1/gameflow-phase"
    expected = base64.b64encode(b"riot:clave-local").decode()
    assert request.headers["Authorization"] == f"Basic {expected}"


def test_client_cannot_call_other_paths():
    client = make_client(lambda r: httpx.Response(200, json={}))
    with pytest.raises(LeagueClientError, match="no permitida"):
        client._get("/lol-champ-select/v1/session/actions/1")
    # La clase no tiene ningún método que modifique el cliente.
    assert not [m for m in dir(LeagueClient) if m.startswith(("post", "patch", "put", "delete", "pick", "ban", "lock"))]
    assert ALLOWED_PATHS == {"/lol-gameflow/v1/gameflow-phase", "/lol-champ-select/v1/session"}


def test_session_404_means_no_champ_select():
    assert make_client(lambda r: httpx.Response(404)).champ_select_session() is None


def test_auth_error_is_readable():
    with pytest.raises(LeagueClientError, match="lockfile"):
        make_client(lambda r: httpx.Response(401)).gameflow_phase()


def test_verified_context_keeps_riot_ca_but_allows_missing_aki():
    from draftmind.integrations.league_client import _verified_context

    context = _verified_context()
    assert context.verify_mode == ssl.CERT_REQUIRED          # Se sigue validando la firma.
    assert not context.verify_flags & ssl.VERIFY_X509_STRICT  # El certificado real no tiene AKI.
    assert len(context.get_ca_certs()) == 1                   # Solo la CA de Riot.


def test_riot_root_certificate_is_bundled_and_valid():
    context = ssl.create_default_context(cafile=str(RIOT_ROOT_CERT))
    subject = dict(x[0] for x in context.get_ca_certs()[0]["subject"])
    assert subject["organizationName"] == "Riot Games"


# --- Sesión ---------------------------------------------------------------------------

def test_parse_session_teams_positions_and_intents():
    draft = parse_session(SESSION, KEYS)
    assert draft.me.champion_id == "Ahri" and draft.me.is_intent and draft.me.role is Role.MIDDLE
    allies = {a.cell_id: a for a in draft.allies}
    assert allies[0].champion_id == "Malphite" and not allies[0].is_intent and allies[0].role is Role.TOP
    assert allies[1].champion_id == "Amumu" and allies[1].is_intent
    assert allies[4].champion_id is None and allies[4].role is None


def test_enemy_intents_are_never_used():
    draft = parse_session(SESSION, KEYS)
    assert [e.champion_id for e in draft.enemies] == ["Darius", None, None]  # LeeSin solo estaba en hover.
    assert all(e.role is None for e in draft.enemies)


def test_bans_merge_sources_and_skip_incomplete_actions():
    draft = parse_session(SESSION, KEYS)
    assert draft.bans == ["Zed", "Leona", "Yasuo"]  # 103 (Ahri) no se completó.


def test_unknown_champion_keys_are_reported():
    assert parse_session(SESSION, KEYS).unknown_champion_keys == [99999]


def test_no_player_names_or_ids_survive_parsing():
    dumped = parse_session(SESSION, KEYS).model_dump_json()
    for forbidden in ("NoDebeMostrarse", "YoMismo", "Enemigo", "secreto", "summonerId", "puuid", "gameName"):
        assert forbidden not in dumped


def test_parse_tolerates_garbage():
    garbage = {"myTeam": [{"cellId": "x"}, {}, "no-dict"], "theirTeam": [None],
               "actions": [["no-dict", {"type": "ban"}], "tampoco"], "bans": {"myTeamBans": None}}
    draft = parse_session(garbage, KEYS)
    assert draft.me is None and draft.allies == [] and draft.enemies == [] and draft.bans == []


# --- Servicio ---------------------------------------------------------------------------

class FakeLeague:
    def __init__(self, phase="ChampSelect", session=SESSION, error=None):
        self.phase, self.session, self.error = phase, session, error
        self.certificate_verified = True

    def gameflow_phase(self):
        if self.error:
            raise LeagueClientError(self.error)
        return self.phase

    def champ_select_session(self):
        return self.session


def service(lock=LOCK, fake=None, keys=KEYS):
    fake = fake or FakeLeague()
    return LiveDraftService(Path("C:/LoL"), lambda: keys, lockfile_reader=lambda _: lock,
                            client_factory=lambda _: fake)


def test_service_states():
    assert service(lock=None).poll().state is LiveState.NO_CLIENT
    assert service(fake=FakeLeague(phase="Lobby")).poll().message == "Cliente abierto, en una sala."
    status = service().poll()
    assert status.state is LiveState.CHAMP_SELECT and status.draft.me.champion_id == "Ahri"
    assert service(fake=FakeLeague(error="cerrándose")).poll().state is LiveState.ERROR


def test_service_does_not_read_during_game():
    fake = FakeLeague(phase="InProgress")
    fake.champ_select_session = lambda: pytest.fail("No debe leerse nada durante la partida")
    status = service(fake=fake).poll()
    assert status.state is LiveState.IN_GAME and status.draft is None


def test_service_needs_champion_keys():
    status = service(keys={}).poll()
    assert status.state is LiveState.ERROR and "Data Dragon" in status.message


def test_settings_default_to_disabled():
    from draftmind.data.database import create_db_engine, init_database
    from draftmind.data.repositories.settings_repository import SettingsRepository

    repo = SettingsRepository(init_database(create_db_engine(None)))
    assert repo.live_draft_enabled is False
    assert str(repo.league_install_dir).endswith("League of Legends")
    repo.live_draft_enabled = True
    repo.league_install_dir = Path("D:/Juegos/LoL")
    assert repo.live_draft_enabled and repo.league_install_dir == Path("D:/Juegos/LoL")
