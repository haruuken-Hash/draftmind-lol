"""Pruebas del cliente de Data Dragon con un servidor simulado (sin Internet)."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from draftmind.domain.enums import EvidenceKind
from draftmind.integrations.data_dragon import (
    DataDragonClient,
    DataDragonError,
    DataDragonUnavailable,
)

FIXTURES = Path(__file__).parents[1] / "fixtures"
FIXTURE = FIXTURES / "champion_16.21.1_es_MX.json"
DATA_FILES = {"item.json", "runesReforged.json", "summoner.json"}
PNG = b"\x89PNG\r\n\x1a\nfake"


class FakeDDragon:
    """Responde como Data Dragon y cuenta las peticiones recibidas."""

    def __init__(self, versions=("16.21.1", "16.20.1"), languages=("es_MX", "en_US")):
        self.versions = list(versions)
        self.languages = set(languages)
        self.requests: list[str] = []
        self.offline = False
        self.status_override: int | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.offline:
            raise httpx.ConnectError("sin red", request=request)
        path = request.url.path
        self.requests.append(path)
        if self.status_override:
            return httpx.Response(self.status_override)
        if path == "/api/versions.json":
            return httpx.Response(200, json=self.versions)
        parts = path.split("/")
        if "/data/" in path:
            version, language, name = parts[2], parts[4], parts[5]
            if version not in self.versions or language not in self.languages:
                return httpx.Response(403)
            if name == "champion.json":
                return httpx.Response(200, content=FIXTURE.read_bytes())
            if name == "champion" and parts[6] == "Kayn.json":
                return httpx.Response(200, content=(FIXTURES / "champion_detail_Kayn.json").read_bytes())
            if name in DATA_FILES:
                return httpx.Response(200, content=(FIXTURES / name).read_bytes())
        if "/img/" in path:
            return httpx.Response(200, content=PNG)
        return httpx.Response(404)


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 28, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


@pytest.fixture
def server():
    return FakeDDragon()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def client(tmp_path, server, clock):
    http = httpx.Client(transport=httpx.MockTransport(server))
    return DataDragonClient(tmp_path / "ddragon", http=http, clock=clock)


def test_parses_champions_and_marks_source_as_official(client):
    catalog = client.champions("16.21.1", "es_MX")
    assert [c.name for c in catalog.champions] == ["Ahri", "Wukong"]  # Ordenados por nombre.
    wukong = catalog.champions[1]
    assert (wukong.id, wukong.key, wukong.image_file) == ("MonkeyKing", 62, "MonkeyKing.png")
    assert wukong.tags == ["Fighter", "Tank"]
    assert catalog.source.kind is EvidenceKind.OFFICIAL
    assert catalog.source.patch == "16.21.1"
    assert catalog.source.retrieved_at is not None


def test_champion_file_is_downloaded_once(client, server):
    client.champions("16.21.1", "es_MX")
    client.champions("16.21.1", "es_MX")
    assert server.requests.count("/cdn/16.21.1/data/es_MX/champion.json") == 1


def test_images_are_cached(client, server):
    path = client.champion_image("16.21.1", "Ahri.png")
    client.champion_image("16.21.1", "Ahri.png")
    assert path.read_bytes() == PNG
    assert len([r for r in server.requests if r.endswith("Ahri.png")]) == 1


def test_versions_are_reused_within_ttl_and_refreshed_after(client, server, clock):
    assert client.versions()[0] == "16.21.1"
    client.versions()
    assert server.requests.count("/api/versions.json") == 1
    clock.now += timedelta(hours=7)
    client.versions()
    assert server.requests.count("/api/versions.json") == 2


def test_offline_uses_saved_versions(client, server, clock):
    client.versions()
    clock.now += timedelta(days=2)
    server.offline = True
    assert client.versions()[0] == "16.21.1"


def test_offline_without_cache_raises_readable_error(client, server):
    server.offline = True
    with pytest.raises(DataDragonError, match="No se pudo conectar"):
        client.versions()


def test_unpublished_version_or_language_is_unavailable(client):
    with pytest.raises(DataDragonUnavailable):
        client.champions("99.1.1", "es_MX")
    with pytest.raises(DataDragonUnavailable):
        client.champions("16.21.1", "xx_XX")


def test_server_error_is_reported(client, server):
    server.status_override = 500
    with pytest.raises(DataDragonError, match="500"):
        client.versions()


def test_corrupt_cache_file_is_discarded(client):
    path = client.champion_file("16.21.1", "es_MX")
    path.parent.mkdir(parents=True)
    path.write_text('{"inesperado": true}', encoding="utf-8")
    with pytest.raises(DataDragonError, match="formato"):
        client.champions("16.21.1", "es_MX")
    assert not path.exists()  # La próxima vez se volverá a descargar.


def test_cached_catalog_picks_newest_version_without_network(client, server):
    client.champions("16.20.1", "es_MX")
    client.champions("16.21.1", "es_MX")
    server.offline = True
    assert client.cached_catalog("es_MX").version == "16.21.1"
    assert client.cached_catalog("en_US") is None


def test_game_data_filters_rift_items(client):
    data = client.game_data("16.21.1", "es_MX")
    names = [i.name for i in data.items]
    # Componentes baratos, abalorios, objetos de otros mapas, copias de Arena (ID de 6
    # cifras) y duplicados quedan fuera.
    assert names == ["Botas de Mercurio", "Malla de Espinas", "Punteras de Acero Revestidas",
                     "Relicario de los Solari de Hierro"]
    thornmail = next(i for i in data.items if i.name == "Malla de Espinas")
    assert thornmail.id == "3075"  # Se conserva el ID más bajo del duplicado.
    steelcaps = next(i for i in data.items if i.id == "3047")
    assert "<" not in steelcaps.description and "Revestimiento" in steelcaps.description


def test_game_data_runes_and_spells(client):
    data = client.game_data("16.21.1", "es_MX")
    assert [p.name for p in data.rune_paths] == ["Dominación", "Valor"]
    domination = data.rune_paths[0]
    assert domination.keystones[0].name == "Electrocutar"
    assert "<b>" not in domination.keystones[0].short_desc
    assert len(domination.minor_slots) == 1
    assert [s.name for s in data.spells] == ["Aplastar", "Destello"]  # Sin hechizos de ARAM.
    assert data.spells[1].cooldown == 300


def test_rune_images_use_unversioned_path(client, server):
    client.rune_image("perk-images/Styles/7200_Domination.png")
    assert "/cdn/img/perk-images/Styles/7200_Domination.png" in server.requests


def test_champion_detail_abilities_tips_and_icons(client, server):
    detail = client.champion_detail("16.21.1", "es_MX", "Kayn")
    assert [a.key for a in detail.abilities] == ["P", "Q", "W", "E", "R"]
    assert detail.abilities[1].name == "Corte Segador" and detail.abilities[1].cooldown[0] == 7
    assert "<b>" not in detail.abilities[0].description and "<i>" not in detail.lore
    assert len(detail.enemy_tips) == 2 and detail.ally_tips
    assert "/cdn/16.21.1/img/spell/KaynQ.png" in server.requests  # Iconos descargados.
    client.champion_detail("16.21.1", "es_MX", "Kayn")
    assert server.requests.count("/cdn/16.21.1/data/es_MX/champion/Kayn.json") == 1  # Caché.


def test_splash_art_uses_unversioned_path(client, server):
    client.splash_art("Kayn")
    assert "/cdn/img/champion/splash/Kayn_0.jpg" in server.requests


def test_clear_cache(client):
    client.champions("16.21.1", "es_MX")
    assert client.cache_size_bytes() > 0
    client.clear_cache()
    assert client.cache_size_bytes() == 0
