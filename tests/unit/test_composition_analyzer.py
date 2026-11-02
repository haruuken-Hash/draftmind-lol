from draftmind.analysis.composition_analyzer import analyze_team, damage_shares


def pick(dataset, *ids):
    by_id = {c.id: c for c in dataset.champions}
    return [by_id[i] for i in ids]


def test_mixed_damage_counts_half_each(dataset):
    physical, magic = damage_shares(pick(dataset, "Kayle"))
    assert physical == magic == 0.5


def test_empty_team_has_no_conclusions():
    team = analyze_team([])
    assert team.strengths == [] and team.weaknesses == []
    assert team.physical_share == 0.0


def test_full_physical_team_without_frontline_is_flagged(dataset):
    team = analyze_team(pick(dataset, "Zed", "MasterYi", "Jinx", "Ezreal", "Vayne"))
    text = " ".join(team.weaknesses)
    assert "físico" in text
    assert "primera línea" in text
    assert "iniciación" in text.lower()


def test_engage_team_is_recognised(dataset):
    team = analyze_team(pick(dataset, "Malphite", "Amumu", "Leona", "Orianna", "Jinx"))
    assert any("iniciar" in s for s in team.strengths)
    assert not any("primera línea" in w for w in team.weaknesses)


def test_few_champions_do_not_produce_gap_warnings(dataset):
    team = analyze_team(pick(dataset, "Zed", "Jinx"))
    assert team.weaknesses == []
