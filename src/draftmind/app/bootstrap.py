"""Montaje de la aplicación: crea las piezas y las conecta.

``AppContext`` agrupa todo lo que necesitan las vistas. Las vistas reciben el
contexto en lugar de crear sus propias dependencias, lo que permite probarlas
con una base de datos en memoria.
"""

import logging
import sys
from dataclasses import dataclass

from draftmind.analysis.draft_analyzer import DraftAnalyzer
from draftmind.analysis.matchup_analyzer import patch_of
from draftmind.app.config import Settings, load_settings
from draftmind.data.database import create_db_engine, init_database
from draftmind.data.demo_data import load_demo_dataset
from draftmind.data.repositories.champion_profile_repository import ChampionProfileRepository
from draftmind.data.repositories.match_repository import MatchRepository
from draftmind.data.repositories.profile_repository import ProfileRepository
from draftmind.data.repositories.research_repository import ResearchRepository
from draftmind.data.repositories.settings_repository import SettingsRepository
from draftmind.domain.models import ChampionCatalog, DemoDataset, GameData
from draftmind.integrations.data_dragon import DataDragonClient
from draftmind.integrations.riot_api import RiotApiClient
from draftmind.services.catalog_service import CatalogService, demo_catalog
from draftmind.services.match_service import MatchService
from draftmind.services.profile_service import build_profiles, observed_positions
from draftmind.services.stats_service import StatsService
from draftmind.utils.logging_config import configure_logging

log = logging.getLogger(__name__)


@dataclass
class AppContext:
    settings: Settings
    dataset: DemoDataset
    profiles: ProfileRepository
    analyzer: DraftAnalyzer
    catalogs: CatalogService
    catalog: ChampionCatalog  # Se sustituye cuando termina la descarga de Data Dragon.
    game_data: GameData | None
    matches: MatchService
    research: ResearchRepository
    stats: StatsService
    app_settings: SettingsRepository
    champion_profiles: ChampionProfileRepository

    def rebuild_profiles(self) -> None:
        """Recalcula los perfiles: estimados (con posiciones observadas en tus partidas
        descargadas) + editoriales + revisados por el usuario."""
        positions = observed_positions(raw for _, raw in self.matches.repository.all_matches())
        self.analyzer.set_champions(
            build_profiles(self.catalog, self.dataset.champions, self.champion_profiles.all(), positions)
        )

    def champion_keys(self) -> dict[int, str]:
        """Número de campeón (el que usa el cliente) -> identificador de Data Dragon."""
        return {c.key: c.id for c in self.catalog.champions if c.key is not None}


def build_context(settings: Settings, in_memory_db: bool = False) -> AppContext:
    engine = create_db_engine(None if in_memory_db else settings.database_path)
    session_factory = init_database(engine)
    profiles = ProfileRepository(session_factory)
    dataset = load_demo_dataset()
    analyzer = DraftAnalyzer(dataset.champions, dataset.source, profiles.get())
    catalogs = CatalogService(DataDragonClient(settings.ddragon_cache_dir), settings.ddragon_language)
    catalog = catalogs.load_cached() or demo_catalog(dataset)
    riot = RiotApiClient(settings.riot_api_key) if settings.has_riot_api_key else None
    stats = StatsService(settings.data_dir / "stats_import.json")
    analyzer.matchup_stats = stats.matchup_stats
    analyzer.current_patch = patch_of(catalog.version)
    ctx = AppContext(
        settings=settings,
        dataset=dataset,
        profiles=profiles,
        analyzer=analyzer,
        catalogs=catalogs,
        catalog=catalog,
        game_data=catalogs.load_cached_game_data(catalog),
        matches=MatchService(MatchRepository(session_factory), riot),
        research=ResearchRepository(session_factory),
        stats=stats,
        app_settings=SettingsRepository(session_factory),
        champion_profiles=ChampionProfileRepository(session_factory),
    )
    ctx.rebuild_profiles()
    return ctx


def run() -> int:
    # Import diferido: la lógica y las pruebas no necesitan cargar Qt.
    from PySide6.QtWidgets import QApplication

    from draftmind.ui.main_window import MainWindow

    settings = load_settings()
    configure_logging(settings.data_dir / "logs", settings.log_level)
    log.info("Iniciando DraftMind LoL (modo demostración: %s)", settings.demo_mode)

    app = QApplication(sys.argv)
    app.setApplicationName("DraftMind LoL")
    window = MainWindow(build_context(settings))
    window.show()
    return app.exec()
