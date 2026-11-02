import pytest

from draftmind.analysis.confidence import assess_confidence
from draftmind.domain.enums import ConfidenceLevel as L


def test_no_data_is_insufficient():
    assert assess_confidence(has_data=False, is_statistical=False).level is L.INSUFFICIENT


def test_qualitative_data_is_never_above_low():
    assert assess_confidence(has_data=True, is_statistical=False).level is L.LOW


@pytest.mark.parametrize("sample, expected", [
    (50, L.INSUFFICIENT),
    (100, L.LOW),
    (999, L.LOW),
    (1000, L.MEDIUM),
    (5000, L.HIGH),
    (None, L.LOW),
])
def test_sample_size_thresholds(sample, expected):
    result = assess_confidence(has_data=True, is_statistical=True, sample_size=sample, same_patch=True)
    assert result.level is expected


def test_other_patch_downgrades_and_warns():
    result = assess_confidence(has_data=True, is_statistical=True, sample_size=10_000, same_patch=False)
    assert result.level is L.MEDIUM
    assert any("parche" in w for w in result.warnings)


def test_stale_and_other_patch_downgrade_twice():
    result = assess_confidence(
        has_data=True, is_statistical=True, sample_size=10_000, same_patch=False, data_age_days=30
    )
    assert result.level is L.LOW
    assert len(result.warnings) == 2
