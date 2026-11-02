import pytest

from draftmind.analysis.draft_analyzer import DraftAnalyzer
from draftmind.domain.enums import ConfidenceLevel, EvidenceKind, ExperienceLevel, Role
from draftmind.domain.models import DraftPick, DraftState, UserProfile


def factor(analysis, key):
    return next(f for f in analysis.factors if f.key == key)


def test_empty_draft_reports_insufficient_context(analyzer):
    a = analyzer.analyze_candidate(DraftState(), "Ahri")
    assert factor(a, "synergy").kind is EvidenceKind.INSUFFICIENT
    assert factor(a, "threats").kind is EvidenceKind.INSUFFICIENT
    assert factor(a, "matchup").kind is EvidenceKind.INSUFFICIENT
    assert a.score == 50  # Sin información no se favorece ni penaliza.
    assert a.pros == [] and a.cons == []


def test_confidence_is_low_and_warns_about_demo_data(analyzer):
    a = analyzer.analyze_candidate(DraftState(my_role=Role.MIDDLE), "Ahri")
    assert a.confidence.level is ConfidenceLevel.LOW
    assert a.confidence.warnings  # Aviso visible: datos sin parche.


def test_role_fit(analyzer):
    draft = DraftState(my_role=Role.UTILITY)
    assert factor(analyzer.analyze_candidate(draft, "Leona"), "role").score > 0
    assert factor(analyzer.analyze_candidate(draft, "Zed"), "role").score < 0


def test_frontline_fills_team_gap(analyzer):
    draft = DraftState(
        my_role=Role.TOP,
        allies=[DraftPick(champion_id=i) for i in ("Zed", "Jinx", "Janna", "MasterYi")],
    )
    malphite = analyzer.analyze_candidate(draft, "Malphite")
    kayle = analyzer.analyze_candidate(draft, "Kayle")
    assert factor(malphite, "synergy").score > factor(kayle, "synergy").score
    assert malphite.score > kayle.score


def test_damage_balance_is_considered(analyzer):
    draft = DraftState(allies=[DraftPick(champion_id=i) for i in ("Zed", "Jinx", "Darius")])
    assert factor(analyzer.analyze_candidate(draft, "Orianna"), "synergy").score > 0
    assert any("físico" in c for c in analyzer.analyze_candidate(draft, "Ezreal").cons)


def test_disengage_answers_heavy_engage(analyzer):
    draft = DraftState(enemies=[DraftPick(champion_id=i) for i in ("Malphite", "Amumu", "Leona")])
    assert factor(analyzer.analyze_candidate(draft, "Janna"), "threats").score > 0
    assert factor(analyzer.analyze_candidate(draft, "Zed"), "threats").score < 0


def test_matchup_admits_missing_statistics(analyzer):
    draft = DraftState(
        my_role=Role.TOP, enemies=[DraftPick(champion_id="Darius", role=Role.TOP)]
    )
    f = factor(analyzer.analyze_candidate(draft, "Kayle"), "matchup")
    assert "evidencia insuficiente" in f.explanation
    assert f.score < 0
    assert abs(f.score) <= 0.5  # Peso limitado: es solo cualitativo.


def test_preferences_adjust_but_do_not_exclude(dataset):
    profile = UserProfile(favorite_champions=["Ahri"], experience=ExperienceLevel.BEGINNER)
    analyzer = DraftAnalyzer(dataset.champions, dataset.source, profile)
    draft = DraftState(my_role=Role.MIDDLE)
    assert factor(analyzer.analyze_candidate(draft, "Ahri"), "preferences").score > 0
    assert factor(analyzer.analyze_candidate(draft, "Orianna"), "preferences").score < 0
    names = [a.champion.id for a in analyzer.suggest_candidates(draft, limit=10)]
    assert "Orianna" in names  # Se penaliza, pero sigue siendo una alternativa.


def test_suggestions_respect_role_and_exclude_taken(analyzer):
    draft = DraftState(
        my_role=Role.UTILITY, allies=[DraftPick(champion_id="Leona")]
    )
    suggestions = analyzer.suggest_candidates(draft, limit=10)
    assert suggestions
    assert all(Role.UTILITY in a.champion.roles for a in suggestions)
    assert "Leona" not in {a.champion.id for a in suggestions}
    scores = [a.score for a in suggestions]
    assert scores == sorted(scores, reverse=True)


def test_scores_stay_in_range(analyzer, dataset):
    draft = DraftState(
        my_role=Role.BOTTOM,
        allies=[DraftPick(champion_id=i) for i in ("Kayle", "MasterYi", "Kassadin")],
        enemies=[DraftPick(champion_id=i) for i in ("Leona", "Nautilus", "Sejuani", "Malphite")],
    )
    for c in dataset.champions:
        if c.id in {"Kayle", "MasterYi", "Kassadin", "Leona", "Nautilus", "Sejuani", "Malphite"}:
            continue
        a = analyzer.analyze_candidate(draft, c.id)
        assert 0 <= a.score <= 100
        assert all(-2 <= f.score <= 2 for f in a.factors)


def test_champions_without_profile_are_reported_and_ignored(analyzer):
    draft = DraftState(
        my_role=Role.MIDDLE,
        allies=[DraftPick(champion_id="Aatrox", role=Role.TOP)],
        enemies=[DraftPick(champion_id="Syndra", role=Role.MIDDLE)],
    )
    assert analyzer.missing_profiles(draft) == ["Aatrox", "Syndra"]
    a = analyzer.analyze_candidate(draft, "Ahri")
    assert "no tiene perfil" in factor(a, "matchup").explanation
    allies, enemies = analyzer.compositions(draft)
    assert allies.champion_ids == [] and enemies.champion_ids == []


def test_unknown_champion_raises(analyzer):
    with pytest.raises(ValueError):
        analyzer.analyze_candidate(DraftState(), "NoExiste")
