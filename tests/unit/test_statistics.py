import json
from datetime import datetime, timedelta, timezone

import pytest

from draftmind.analysis.draft_analyzer import DraftAnalyzer
from draftmind.analysis.matchup_analyzer import analyze_matchup, evaluate_stat, patch_of
from draftmind.domain.enums import ConfidenceLevel, EvidenceKind, Role
from draftmind.domain.models import ChampionStat, DataSource, DraftPick, DraftState, MatchSummary, UserProfile
from draftmind.integrations.statistics_providers import (
    ImportedStatsProvider,
    PersonalStatsProvider,
    StatsImportError,
    consistency_warnings,
)
from draftmind.services.stats_service import StatsService

NOW = datetime(2026, 10, 28, tzinfo=timezone.utc)


def game(i, champ="Garen", opp="Darius", win=True, patch="16.21", role=Role.TOP):
    return MatchSummary(match_id=str(i), platform="LA1", puuid="P", champion_id=champ, role=role, win=win,
                        duration_s=1800, patch=patch, lane_opponent=opp, played_at=NOW)


def source(days_old=1, name="Fuente X"):
    return DataSource(name=name, kind=EvidenceKind.OBSERVED, retrieved_at=NOW - timedelta(days=days_old))


IMPORT = {
    "source": {"name": "Fuente de prueba", "url": "https://example.org/datos",
               "retrieved_at": "2026-10-27T10:00:00Z"},
    "patch": "16.21", "region": "LAN", "rank_segment": "Oro+",
    "rows": [
        {"champion_id": "Garen", "role": "TOP", "games": 20000, "win_rate": 0.51},
        {"champion_id": "Garen", "role": "TOP", "opponent_id": "Darius", "games": 6000, "win_rate": 0.47},
        {"champion_id": "Garen", "role": "TOP", "opponent_id": "Malphite", "games": 50, "wins": 30},
    ],
}


# --- Proveedor personal -----------------------------------------------------------

def test_personal_stats_count_wins_and_opponents():
    provider = PersonalStatsProvider([game(1), game(2, win=False), game(3, opp="Malphite")], demo=False, region="LA1")
    stat = provider.matchup_stats("Garen", "Darius")[0]
    assert (stat.games, stat.wins, stat.observed_win_rate) == (2, 1, 0.5)
    assert [s.opponent_id for s in provider.opponents("Garen")] == ["Darius", "Malphite"]
    assert provider.champion_stats("Garen")[0].games == 3
    assert provider.matchup_stats("Garen", "Zed") == []


def test_personal_stats_flag_mixed_patches_and_skip_remakes():
    remake = game(9).model_copy(update={"duration_s": 120})
    provider = PersonalStatsProvider([game(1, patch="16.20"), game(2, patch="16.21"), remake], demo=False, region=None)
    stat = provider.champion_stats("Garen")[0]
    assert stat.games == 2 and stat.patch is None
    assert "16.20" in stat.source.notes and "16.21" in stat.source.notes


# --- Importación ----------------------------------------------------------------------

def test_import_valid_file(tmp_path):
    path = tmp_path / "stats.json"
    path.write_text(json.dumps(IMPORT), encoding="utf-8")
    provider = ImportedStatsProvider.from_file(path)
    stat = provider.matchup_stats("Garen", "Darius", Role.TOP)[0]
    assert stat.games == 6000 and stat.region == "LAN" and stat.source.url == "https://example.org/datos"
    assert stat.pick_rate is None  # No se inventa lo que la fuente no da.
    assert provider.champion_stats("Garen", Role.TOP)[0].win_rate == 0.51


def test_documented_example_file_is_valid():
    from pathlib import Path

    example = Path(__file__).parents[2] / "docs" / "examples" / "stats_import_example.json"
    provider = ImportedStatsProvider.from_file(example)
    assert "ficticios" in provider.name


def test_import_rejects_missing_source(tmp_path):
    bad = dict(IMPORT)
    del bad["source"]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(StatsImportError, match="source"):
        ImportedStatsProvider.from_file(path)


def test_import_rejects_impossible_win_rate(tmp_path):
    bad = json.loads(json.dumps(IMPORT))
    bad["rows"][0]["win_rate"] = 51  # Porcentaje en lugar de proporción.
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(StatsImportError):
        ImportedStatsProvider.from_file(path)


def test_stats_service_persists_import(tmp_path):
    original = tmp_path / "descarga.json"
    original.write_text(json.dumps(IMPORT), encoding="utf-8")
    service = StatsService(tmp_path / "data" / "stats_import.json")
    service.import_file(original)
    reopened = StatsService(tmp_path / "data" / "stats_import.json")
    assert reopened.imported is not None
    reopened.remove_import()
    assert StatsService(tmp_path / "data" / "stats_import.json").imported is None


# --- Normalización y evidencia ------------------------------------------------------------

def test_consistency_warnings():
    a = ChampionStat(champion_id="Garen", games=10, source=source(), patch="16.20", region="LAN")
    b = ChampionStat(champion_id="Garen", games=10, source=source(), patch="16.21", region="EUW")
    warnings = consistency_warnings([a, b])
    assert any("parches" in w for w in warnings) and any("regiones" in w for w in warnings)


def test_evaluate_stat_reference_and_confidence():
    stat = ChampionStat(champion_id="Garen", opponent_id="Darius", games=6000, win_rate=0.47,
                        patch="16.21", source=source())
    reference = ChampionStat(champion_id="Garen", games=20000, win_rate=0.51, patch="16.21", source=source())
    ev = evaluate_stat(stat, reference, "16.21", NOW)
    assert ev.difference_pp == pytest.approx(-4.0)
    assert ev.confidence.level is ConfidenceLevel.HIGH
    assert "no demuestra" in ev.text


def test_old_patch_and_stale_data_lower_confidence():
    stat = ChampionStat(champion_id="Garen", games=6000, win_rate=0.47, patch="16.19", source=source(days_old=40))
    ev = evaluate_stat(stat, None, "16.21", NOW)
    assert ev.confidence.level is ConfidenceLevel.LOW
    assert len(ev.confidence.warnings) == 2
    assert ev.reference == 0.5


def test_patch_of():
    assert patch_of("16.21.1") == "16.21"
    assert patch_of(None) is None


# --- Enfrentamientos -------------------------------------------------------------------------

def test_matchup_with_small_personal_sample_is_insufficient(dataset):
    profiles = {c.id: c for c in dataset.champions}
    provider = PersonalStatsProvider([game(1), game(2)], demo=False, region="LA1")
    result = analyze_matchup("Garen", "Darius", Role.TOP, [provider], profiles, UserProfile(), "16.21", NOW)
    assert result.confidence.level is ConfidenceLevel.INSUFFICIENT
    assert result.evidence[0].stat.games == 2
    assert all(i.kind is not EvidenceKind.OBSERVED for i in result.insights)
    assert any("presión temprana" in i.text for i in result.insights)


def test_matchup_never_claims_absolute_counter(dataset):
    profiles = {c.id: c for c in dataset.champions}
    result = analyze_matchup("Kayle", "Darius", Role.TOP, [], profiles, UserProfile(), "16.21", NOW)
    text = " ".join(i.text for i in result.insights).lower()
    assert "counter" not in text and "siempre" not in text
    assert result.confidence.level is ConfidenceLevel.LOW


def test_matchup_without_profiles_or_stats(dataset):
    result = analyze_matchup("Aatrox", "Syndra", None, [], {}, UserProfile(), None, NOW)
    assert result.confidence.level is ConfidenceLevel.INSUFFICIENT
    assert result.insights[0].kind is EvidenceKind.INSUFFICIENT


def test_draft_analyzer_uses_observed_stats_when_sample_is_enough(dataset, tmp_path):
    path = tmp_path / "stats.json"
    path.write_text(json.dumps(IMPORT), encoding="utf-8")
    provider = ImportedStatsProvider.from_file(path)
    analyzer = DraftAnalyzer(dataset.champions, dataset.source)
    analyzer.matchup_stats = lambda c, o, r: provider.matchup_stats(c, o, r)
    analyzer.current_patch = "16.21"
    draft = DraftState(my_role=Role.TOP, enemies=[DraftPick(champion_id="Darius", role=Role.TOP)])
    f = next(x for x in analyzer.analyze_candidate(draft, "Garen").factors if x.key == "matchup")
    assert f.kind is EvidenceKind.OBSERVED and f.score < 0
    assert "6000 partidas" in f.explanation

    draft_small = DraftState(my_role=Role.TOP, enemies=[DraftPick(champion_id="Malphite", role=Role.TOP)])
    f_small = next(x for x in analyzer.analyze_candidate(draft_small, "Garen").factors if x.key == "matchup")
    assert f_small.kind is EvidenceKind.INFERENCE
    assert "muestra es insuficiente" in f_small.explanation
