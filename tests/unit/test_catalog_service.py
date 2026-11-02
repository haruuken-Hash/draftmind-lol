import httpx

from draftmind.integrations.data_dragon import DataDragonClient
from draftmind.services.catalog_service import CatalogService, demo_catalog
from tests.unit.test_data_dragon import FakeDDragon


def make_service(tmp_path, server, language="es_MX"):
    http = httpx.Client(transport=httpx.MockTransport(server))
    return CatalogService(DataDragonClient(tmp_path, http=http), language)


def test_refresh_downloads_catalog_and_portraits(tmp_path):
    service = make_service(tmp_path, FakeDDragon())
    progress = []
    result = service.refresh(lambda done, total: progress.append((done, total)))
    assert result.catalog.version == "16.21.1"
    assert result.warnings == []
    assert result.game_data is not None and len(result.game_data.items) == 4
    # 2 retratos + 4 objetos + 2 hechizos + 2 árboles + 2 claves de runas.
    assert progress[-1] == (12, 12)
    for champion in result.catalog.champions:
        assert service.image_path(result.catalog, champion) is not None
    assert service.load_cached_game_data(result.catalog) is not None


def test_missing_language_falls_back_to_english_with_warning(tmp_path):
    service = make_service(tmp_path, FakeDDragon(languages=("en_US",)))
    result = service.refresh()
    assert result.catalog.language == "en_US"
    assert any("en_US" in w for w in result.warnings)


def test_failed_portraits_are_reported_not_fatal(tmp_path):
    server = FakeDDragon()
    original = server.__call__

    def no_images(request):
        if "/img/" in request.url.path:
            return httpx.Response(500)
        return original(request)

    service = make_service(tmp_path, no_images)
    result = service.refresh()
    assert any("12 imágenes" in w for w in result.warnings)


def test_load_cached_after_refresh(tmp_path):
    service = make_service(tmp_path, FakeDDragon())
    assert service.load_cached() is None
    service.refresh()
    assert service.load_cached().version == "16.21.1"


def test_demo_catalog_has_no_version(dataset):
    catalog = demo_catalog(dataset)
    assert not catalog.from_data_dragon
    assert len(catalog.champions) == len(dataset.champions)
