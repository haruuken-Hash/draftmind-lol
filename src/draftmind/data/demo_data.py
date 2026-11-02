"""Carga del conjunto de datos de demostración incluido con la aplicación."""

import json
from pathlib import Path

from draftmind.domain.models import DemoDataset

DEMO_CHAMPIONS_FILE = Path(__file__).resolve().parents[1] / "resources" / "demo" / "champions_demo.json"


def load_demo_dataset(path: Path = DEMO_CHAMPIONS_FILE) -> DemoDataset:
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)
    # model_validate lanza ValidationError si algún campo es incorrecto.
    dataset = DemoDataset.model_validate(raw)
    ids = [c.id for c in dataset.champions]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"Campeones duplicados en {path.name}: {sorted(duplicates)}")
    return dataset
