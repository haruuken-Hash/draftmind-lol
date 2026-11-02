"""Cliente de Data Dragon (datos estáticos oficiales de Riot) con caché en disco.

Endpoints usados (comprobados el 28/10/2026):
  /api/versions.json                                   versiones, la primera es la más reciente
  /cdn/{version}/data/{idioma}/champion.json           lista de campeones
  /cdn/{version}/img/champion/{archivo}                retrato cuadrado (PNG)
Una versión o idioma inexistente responde 403.

Estructura de la caché:
  {cache_dir}/versions.json                 lista de versiones + fecha de consulta
  {cache_dir}/{version}/{idioma}/champion.json
  {cache_dir}/{version}/img/champion/*.png

Data Dragon solo ofrece datos ESTÁTICOS (nombres, clases, imágenes). No dice
nada sobre win rates ni sobre qué campeón es mejor.
"""

import json
import logging
import shutil
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from pydantic import TypeAdapter, ValidationError

from draftmind.domain.enums import EvidenceKind
from draftmind.domain.models import (
    ChampionCatalog,
    ChampionInfo,
    DataSource,
    GameData,
    ItemInfo,
    RuneInfo,
    RunePathInfo,
    SpellInfo,
)
from draftmind.domain.schemas import (
    DDragonChampionFile,
    DDragonItemFile,
    DDragonRunePath,
    DDragonSpellFile,
)
from draftmind.utils.text import strip_html

log = logging.getLogger(__name__)

BASE_URL = "https://ddragon.leagueoflegends.com"
VERSIONS_TTL = timedelta(hours=6)  # No se vuelve a preguntar por versiones antes de esto.


class DataDragonError(Exception):
    """Error comprensible para el usuario al usar Data Dragon."""


class DataDragonUnavailable(DataDragonError):
    """La versión o el idioma pedidos todavía no están publicados."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _write_atomic(path: Path, data: bytes) -> None:
    # Escribe en un temporal y lo renombra: si se corta, no queda un archivo a medias.
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


class DataDragonClient:
    def __init__(
        self,
        cache_dir: Path,
        http: httpx.Client | None = None,
        base_url: str = BASE_URL,
        clock: Callable[[], datetime] = _now,
    ):
        self.cache_dir = cache_dir
        self._http = http or httpx.Client(timeout=20, follow_redirects=True)
        self._base = base_url.rstrip("/")
        self._clock = clock

    # --- HTTP --------------------------------------------------------------

    def _get(self, path: str) -> httpx.Response:
        url = f"{self._base}{path}"
        try:
            response = self._http.get(url)
        except httpx.HTTPError as exc:
            raise DataDragonError(f"No se pudo conectar con Data Dragon ({exc.__class__.__name__}).") from exc
        if response.status_code in (403, 404):
            raise DataDragonUnavailable(f"Recurso no disponible en Data Dragon: {path}")
        if response.status_code >= 400:
            raise DataDragonError(f"Data Dragon respondió con el código {response.status_code}.")
        return response

    # --- Versiones ---------------------------------------------------------

    def versions(self) -> list[str]:
        """Versiones publicadas. Usa la copia local si se consultó hace poco."""
        cache_file = self.cache_dir / "versions.json"
        cached = self._read_versions_cache(cache_file)
        if cached and self._clock() - cached[0] < VERSIONS_TTL:
            return cached[1]
        try:
            versions = self._get("/api/versions.json").json()
        except DataDragonError:
            if cached:
                log.warning("Sin conexión con Data Dragon; se usan las versiones guardadas.")
                return cached[1]
            raise
        if not isinstance(versions, list) or not versions:
            raise DataDragonError("La lista de versiones de Data Dragon tiene un formato inesperado.")
        payload = {"retrieved_at": self._clock().isoformat(), "versions": versions}
        _write_atomic(cache_file, json.dumps(payload).encode("utf-8"))
        return versions

    @staticmethod
    def _read_versions_cache(path: Path) -> tuple[datetime, list[str]] | None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return datetime.fromisoformat(raw["retrieved_at"]), list(raw["versions"])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    # --- Campeones ---------------------------------------------------------

    def champion_file(self, version: str, language: str) -> Path:
        return self.cache_dir / version / language / "champion.json"

    def image_path(self, version: str, image_file: str) -> Path:
        return self.cache_dir / version / "img" / "champion" / image_file

    def champions(self, version: str, language: str) -> ChampionCatalog:
        """Catálogo de una versión e idioma. Solo descarga si no está en caché."""
        path = self.champion_file(version, language)
        if not path.exists():
            response = self._get(f"/cdn/{version}/data/{language}/champion.json")
            _write_atomic(path, response.content)
        return self._parse_catalog(path, version, language)

    def _parse_catalog(self, path: Path, version: str, language: str) -> ChampionCatalog:
        try:
            parsed = DDragonChampionFile.model_validate_json(path.read_bytes())
        except ValidationError as exc:
            path.unlink(missing_ok=True)  # Archivo corrupto: que se vuelva a descargar.
            raise DataDragonError("El archivo de campeones de Data Dragon no tiene el formato esperado.") from exc
        champions = [
            ChampionInfo(
                id=c.id, key=c.key, name=c.name, title=c.title, tags=c.tags, image_file=c.image.full,
                attack=c.info.attack, defense=c.info.defense, magic=c.info.magic,
                difficulty=c.info.difficulty, attack_range=c.stats.attackrange,
            )
            for c in parsed.data.values()
        ]
        champions.sort(key=lambda c: c.name)
        retrieved = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        return ChampionCatalog(
            source=DataSource(
                name="Data Dragon (Riot Games)",
                kind=EvidenceKind.OFFICIAL,
                url=f"{self._base}/cdn/{version}/data/{language}/champion.json",
                patch=version,
                retrieved_at=retrieved,
                notes="Datos estáticos oficiales: nombres, clases e imágenes. No contiene estadísticas de rendimiento.",
            ),
            version=version,
            language=language,
            champions=champions,
        )

    def champion_image(self, version: str, image_file: str) -> Path:
        path = self.image_path(version, image_file)
        if not path.exists():
            response = self._get(f"/cdn/{version}/img/champion/{image_file}")
            _write_atomic(path, response.content)
        return path

    # --- Objetos, runas y hechizos -------------------------------------------

    def _data_file(self, version: str, language: str, name: str) -> bytes:
        path = self.cache_dir / version / language / name
        if not path.exists():
            response = self._get(f"/cdn/{version}/data/{language}/{name}")
            _write_atomic(path, response.content)
        return path.read_bytes()

    def game_data(self, version: str, language: str) -> GameData:
        """Objetos de la Grieta, árboles de runas y hechizos de invocador."""
        try:
            items_file = DDragonItemFile.model_validate_json(self._data_file(version, language, "item.json"))
            paths = TypeAdapter(list[DDragonRunePath]).validate_json(
                self._data_file(version, language, "runesReforged.json")
            )
            spells_file = DDragonSpellFile.model_validate_json(self._data_file(version, language, "summoner.json"))
        except ValidationError as exc:
            for name in ("item.json", "runesReforged.json", "summoner.json"):
                (self.cache_dir / version / language / name).unlink(missing_ok=True)
            raise DataDragonError("Los datos de objetos, runas o hechizos no tienen el formato esperado.") from exc

        return GameData(
            source=DataSource(
                name="Data Dragon (Riot Games)",
                kind=EvidenceKind.OFFICIAL,
                url=f"{self._base}/cdn/{version}/data/{language}/item.json",
                patch=version,
                retrieved_at=self._clock(),
                notes="Objetos, runas y hechizos oficiales. Describen qué hace cada elemento, no cuál rinde mejor.",
            ),
            version=version,
            language=language,
            items=_rift_items(items_file),
            item_names={item_id: item.name for item_id, item in items_file.data.items()},
            rune_paths=[_rune_path(p) for p in paths],
            spells=sorted(
                (
                    SpellInfo(
                        id=s.id, key=s.key, name=s.name, description=strip_html(s.description),
                        cooldown=s.cooldown[0] if s.cooldown else None, image_file=s.image.full,
                    )
                    for s in spells_file.data.values()
                    if "CLASSIC" in s.modes  # Solo los disponibles en partidas normales de la Grieta.
                ),
                key=lambda s: s.name,
            ),
        )

    def item_image(self, version: str, image_file: str) -> Path:
        return self._image(f"{version}/img/item/{image_file}")

    def spell_image(self, version: str, image_file: str) -> Path:
        return self._image(f"{version}/img/spell/{image_file}")

    def rune_image(self, icon: str) -> Path:
        # Los iconos de runas no llevan versión en la URL (comprobado).
        return self._image(f"img/{icon}")

    def _image(self, relative: str) -> Path:
        path = self.cache_dir / "assets" / relative
        if not path.exists():
            response = self._get(f"/cdn/{relative}")
            _write_atomic(path, response.content)
        return path

    def cached_image(self, relative: str) -> Path | None:
        path = self.cache_dir / "assets" / relative
        return path if path.exists() else None

    def cached_catalog(self, language: str) -> ChampionCatalog | None:
        """Catálogo más reciente que ya esté en disco, sin usar la red."""
        if not self.cache_dir.exists():
            return None
        candidates = [p.parent.parent.name for p in self.cache_dir.glob(f"*/{language}/champion.json")]
        for version in sorted(candidates, key=_version_key, reverse=True):
            try:
                return self._parse_catalog(self.champion_file(version, language), version, language)
            except DataDragonError:
                continue
        return None

    # --- Mantenimiento -----------------------------------------------------

    def cache_size_bytes(self) -> int:
        if not self.cache_dir.exists():
            return 0
        return sum(p.stat().st_size for p in self.cache_dir.rglob("*") if p.is_file())

    def clear_cache(self) -> None:
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)


SUMMONERS_RIFT = "11"
MIN_COMPLETED_GOLD = 900
MAX_RIFT_ITEM_ID_DIGITS = 4
EXCLUDED_ITEM_TAGS = {"Consumable", "Trinket"}


def _rift_items(items_file: DDragonItemFile) -> list[ItemInfo]:
    """Objetos comprables y completos de la Grieta, sin duplicados.

    Criterio (decisión propia, documentada): disponible en el mapa 11,
    comprable, sin campeón obligatorio, no consumible ni abalorio, coste total
    >= 900 y que no se mejore a otro objeto (salvo las botas).
    Data Dragon repite objetos con ID de 6 cifras para otros modos (p. ej.
    Arena: 663193, 667109...), a veces marcados también para el mapa 11; por
    eso solo se aceptan ID de hasta 4 cifras (comprobado con 16.21.1).
    """
    by_name: dict[str, ItemInfo] = {}
    for item_id, item in sorted(items_file.data.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
        if not item_id.isdigit() or len(item_id) > MAX_RIFT_ITEM_ID_DIGITS:
            continue
        if not item.maps.get(SUMMONERS_RIFT) or not item.gold.purchasable:
            continue
        if item.inStore is False or item.requiredChampion or EXCLUDED_ITEM_TAGS & set(item.tags):
            continue
        if item.gold.total < MIN_COMPLETED_GOLD or (item.into and "Boots" not in item.tags):
            continue
        by_name.setdefault(item.name, ItemInfo(
            id=item_id, name=item.name, plaintext=item.plaintext,
            description=strip_html(item.description), total_gold=item.gold.total,
            tags=item.tags, image_file=item.image.full, builds_from=item.from_,
        ))
    return sorted(by_name.values(), key=lambda i: i.name)


def _rune_path(path: DDragonRunePath) -> RunePathInfo:
    def info(r):
        return RuneInfo(id=r.id, key=r.key, name=r.name, short_desc=strip_html(r.shortDesc), icon=r.icon)

    return RunePathInfo(
        id=path.id, key=path.key, name=path.name, icon=path.icon,
        keystones=[info(r) for r in path.slots[0].runes] if path.slots else [],
        minor_slots=[[info(r) for r in slot.runes] for slot in path.slots[1:]],
    )


def _version_key(version: str) -> tuple[int, ...]:
    """'16.21.1' -> (16, 21, 1) para ordenar numéricamente."""
    try:
        return tuple(int(p) for p in version.split("."))
    except ValueError:
        return (0,)
