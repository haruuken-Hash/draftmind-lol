import json

import pytest
from pydantic import ValidationError

from draftmind.data.demo_data import load_demo_dataset
from draftmind.domain.enums import EvidenceKind, Role


def test_demo_dataset_loads_and_covers_every_role(dataset):
    assert len(dataset.champions) >= 20
    for role in Role:
        assert any(role in c.roles for c in dataset.champions), role


def test_demo_source_is_labelled_as_non_statistical(dataset):
    assert dataset.source.kind is EvidenceKind.EDUCATIONAL
    assert dataset.source.patch is None


def _write(tmp_path, champions):
    path = tmp_path / "demo.json"
    path.write_text(json.dumps({
        "source": {"name": "test", "kind": "educativo"},
        "champions": champions,
    }), encoding="utf-8")
    return path


BASE = {"id": "X", "name": "X", "roles": ["TOP"], "damage_type": "PHYSICAL", "engage": 1,
        "disengage": 1, "cc": 1, "early": 1, "scaling": 1, "frontline": 1,
        "difficulty": 1, "resource_dependence": 1}


def test_out_of_range_attribute_is_rejected(tmp_path):
    with pytest.raises(ValidationError):
        load_demo_dataset(_write(tmp_path, [{**BASE, "engage": 7}]))


def test_duplicate_champions_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="duplicados"):
        load_demo_dataset(_write(tmp_path, [BASE, BASE]))
