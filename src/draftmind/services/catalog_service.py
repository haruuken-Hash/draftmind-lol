"""Obtiene el catálogo de campeones: Data Dragon si se puede, demo si no.

Orden de preferencia:
1. Catálogo en caché (instantáneo, sin red) al arrancar.
2. ``refresh()`` en segundo plano: última versión publicada + retratos.
3. Si nunca hubo conexión: catálogo mínimo con los campeones de demostración.
"""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from draftmind.domain.models import ChampionCatalog, ChampionInfo, DemoDataset, GameData
from draftmind.integrations.data_dragon import (
    DataDragonClient,
    DataDragonError,
    DataDragonUnavailable,
)

log = logging.getLogger(__name__)

FALLBACK_LANGUAGE = "en_US"
IMAGE_WORKERS = 8

Progress = Callable[[int, int], None]


@dataclass
class RefreshResult:
    catalog: ChampionCatalog
    game_data: GameData | None = None
    warnings: list[str] = field(default_factory=list)


def demo_catalog(dataset: DemoDataset) -> ChampionCatalog:
    return ChampionCatalog(
        source=dataset.source,
        champions=sorted(
            (ChampionInfo(id=c.id, name=c.name) for c in dataset.champions),
            key=lambda c: c.name,
        ),
    )


class CatalogService:
    def __init__(self, client: DataDragonClient, language: str):
        self.client = client
        self.language = language

    def load_cached(self) -> ChampionCatalog | None:
        return self.client.cached_catalog(self.language)

    def refresh(self, progress: Progress | None = None) -> RefreshResult:
        """Descarga lo que falte. Lanza DataDragonError si no hay nada utilizable."""
        warnings: list[str] = []
        version = self.client.versions()[0]
        try:
            catalog = self.client.champions(version, self.language)
        except DataDragonUnavailable:
            warnings.append(
                f"Los datos de la versión {version} aún no están disponibles en {self.language}; "
                f"se usan en {FALLBACK_LANGUAGE}."
            )
            catalog = self.client.champions(version, FALLBACK_LANGUAGE)

        version = catalog.version
        downloads = [(self.client.champion_image, version, c.image_file)
                     for c in catalog.champions if c.image_file]

        game_data = None
        try:
            game_data = self.client.game_data(version, catalog.language)
        except DataDragonError as exc:
            warnings.append(f"No se pudieron cargar objetos, runas y hechizos: {exc}")
        if game_data:
            downloads += [(self.client.item_image, version, i.image_file) for i in game_data.items if i.image_file]
            downloads += [(self.client.spell_image, version, s.image_file) for s in game_data.spells if s.image_file]
            for path in game_data.rune_paths:
                downloads.append((self.client.rune_image, path.icon))
                downloads += [(self.client.rune_image, r.icon) for r in path.keystones]

        # Imágenes en paralelo, como mucho IMAGE_WORKERS a la vez para no saturar el CDN.
        failed = 0
        with ThreadPoolExecutor(max_workers=IMAGE_WORKERS) as pool:
            futures = [pool.submit(fn, *args) for fn, *args in downloads]
            for i, future in enumerate(as_completed(futures), start=1):
                try:
                    future.result()
                except DataDragonError as exc:
                    failed += 1
                    log.warning("No se pudo descargar una imagen: %s", exc)
                if progress:
                    progress(i, len(futures))
        if failed:
            warnings.append(f"No se pudieron descargar {failed} imágenes; se mostrarán iniciales.")
        return RefreshResult(catalog=catalog, game_data=game_data, warnings=warnings)

    def load_cached_game_data(self, catalog: ChampionCatalog) -> GameData | None:
        """Objetos, runas y hechizos ya guardados para el catálogo, sin red."""
        if not catalog.version:
            return None
        folder = self.client.cache_dir / catalog.version / catalog.language
        if not all((folder / n).exists() for n in ("item.json", "runesReforged.json", "summoner.json")):
            return None
        try:
            return self.client.game_data(catalog.version, catalog.language)
        except DataDragonError:
            return None

    def image_path(self, catalog: ChampionCatalog, champion: ChampionInfo) -> Path | None:
        """Ruta del retrato si está descargado; None en caso contrario."""
        if not catalog.version or not champion.image_file:
            return None
        path = self.client.image_path(catalog.version, champion.image_file)
        return path if path.exists() else None
