from datetime import datetime, timezone

import pytest

from draftmind.analysis.lane_matchup import analyze_matchup, assign_enemy_roles, gank_danger, gank_options
from draftmind.domain.enums import DamageType, EvidenceKind, ProfileOrigin, Role
from draftmind.domain.models import BaseStats, ChampionProfile, DraftPick, MatchSummary

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def profile(id_: str, roles: list[Role], **attrs) -> ChampionProfile:
    base = dict(engage=1, disengage=1, cc=1, early=1, scaling=1, frontline=1, difficulty=2, resource_dependence=1)
    base.update(attrs)
    return ChampionProfile(id=id_, name=id_, roles=roles, damage_type=DamageType.PHYSICAL, **base)


def stats(**kw) -> BaseStats:
    base = dict(hp=650, hp_per_level=100, armor=35, armor_per_level=4.5, magic_resist=32,
                magic_resist_per_level=2, attack_damage=60, attack_speed=0.65, move_speed=340, attack_range=175)
    base.update(kw)
    return BaseStats(**base)


def match(**kw) -> MatchSummary:
    base = dict(match_id="M", platform="LA1", puuid="P", champion_id="Mine", role=Role.TOP, win=True,
                kills=3, deaths=2, assists=4, duration_s=1800, played_at=NOW, lane_opponent="Rival")
    base.update(kw)
    return MatchSummary(**base)


def test_stat_growth_uses_official_formula():
    s = stats(hp=600, hp_per_level=100)
    assert s.hp_at(1) == 600
    # Nivel 18: 17 × (0,7025 + 0,0175 × 17) = 17 niveles completos de crecimiento.
    assert s.hp_at(18) == pytest.approx(600 + 100 * 17)


def test_base_stats_from_data_dragon_and_missing_data():
    from draftmind.domain.schemas import DDragonStats
    from draftmind.integrations.data_dragon import _base_stats

    # Valores de Darius en 16.21.1.
    parsed = _base_stats(DDragonStats(hp=652, hpperlevel=114, armor=37, armorperlevel=5.2, spellblock=32,
                                      spellblockperlevel=2.05, attackdamage=64, attackspeed=0.625,
                                      movespeed=340, attackrange=175))
    assert parsed.hp == 652 and parsed.armor_per_level == 5.2
    assert _base_stats(DDragonStats(attackrange=175)) is None  # Sin datos: no se inventan.


def test_early_bully_against_scaler_crosses_over():
    mine = profile("Mine", [Role.TOP], early=1, scaling=3)
    rival = profile("Rival", [Role.TOP], early=3, scaling=1, engage=2)
    m = analyze_matchup(mine, rival, Role.TOP, {}, [])
    edges = [p.edge for p in m.phases]
    assert edges[0] == -1 and edges[-1] == 1
    assert "Tu ventana llega en fase tardía (nivel 11+)" in m.summary
    assert m.history.kind is EvidenceKind.INSUFFICIENT


def test_range_and_basic_attack_duel_use_official_stats():
    mine = profile("Mine", [Role.TOP])
    rival = profile("Rival", [Role.TOP])
    data = {"Mine": stats(attack_range=550, attack_damage=70), "Rival": stats()}
    early = analyze_matchup(mine, rival, Role.TOP, data, []).phases[0]
    assert early.edge == 1
    assert EvidenceKind.OFFICIAL in early.kinds
    assert any("Alcance 550 contra 175" in r for r in early.reasons)


def test_range_is_ignored_in_jungle():
    mine, rival = profile("Mine", [Role.JUNGLE]), profile("Rival", [Role.JUNGLE])
    data = {"Mine": stats(attack_range=550), "Rival": stats()}
    early = analyze_matchup(mine, rival, Role.JUNGLE, data, []).phases[0]
    assert not any("Alcance" in r for r in early.reasons)


def test_history_counts_games_against_that_rival_and_gold_diff():
    games = [match(match_id="A", win=True), match(match_id="B", win=False, champion_id="Other"),
             match(match_id="C", lane_opponent="Someone")]
    m = analyze_matchup(profile("Mine", [Role.TOP]), profile("Rival", [Role.TOP]), Role.TOP, {}, games,
                        gold_at_10={"A": 300, "B": -100})
    assert m.history.kind is EvidenceKind.OBSERVED
    assert m.history.sample_size == 2
    assert "1 V - 1 D" in m.history.text and "+100" in m.history.text


def test_estimated_profiles_are_flagged():
    rival = profile("Rival", [Role.TOP]).model_copy(update={"origin": ProfileOrigin.ESTIMATED})
    assert analyze_matchup(profile("Mine", [Role.TOP]), rival, Role.TOP, {}, []).estimated_profiles


def test_assign_enemy_roles_keeps_explicit_and_deduces_unique():
    profiles = {
        "A": profile("A", [Role.TOP, Role.JUNGLE]),
        "B": profile("B", [Role.JUNGLE]),
        "C": profile("C", [Role.MIDDLE, Role.TOP]),
        "D": profile("D", [Role.BOTTOM, Role.MIDDLE]),
    }
    picks = [DraftPick(champion_id="A"), DraftPick(champion_id="B"), DraftPick(champion_id="C"),
             DraftPick(champion_id="D", role=Role.BOTTOM)]
    roles = assign_enemy_roles(picks, profiles)
    assert roles[Role.BOTTOM] == ("D", False)
    assert roles[Role.JUNGLE] == ("B", True)
    assert roles[Role.TOP] == ("A", True)
    assert roles[Role.MIDDLE] == ("C", True)


def test_assign_enemy_roles_does_not_guess_when_ambiguous():
    profiles = {"A": profile("A", [Role.TOP, Role.MIDDLE]), "C": profile("C", [Role.MIDDLE, Role.TOP])}
    assert assign_enemy_roles([DraftPick(champion_id="A"), DraftPick(champion_id="C")], profiles) == {}


def test_gank_options_prefer_immobile_fragile_lane_with_cc_ally():
    allies = {Role.TOP: profile("AT", [Role.TOP], cc=3, engage=2), Role.MIDDLE: profile("AM", [Role.MIDDLE], cc=0, engage=0)}
    enemies = {Role.TOP: profile("ET", [Role.TOP], disengage=0, frontline=1),
               Role.MIDDLE: profile("EM", [Role.MIDDLE], disengage=3, frontline=1)}
    options = gank_options(allies, enemies)
    assert [o.lane for o in options] == [Role.TOP, Role.MIDDLE]
    assert options[0].verdict == "Buen objetivo"
    assert options[1].verdict == "Difícil"


def test_assassin_tag_counts_as_mobility():
    enemies = {Role.MIDDLE: profile("Zed", [Role.MIDDLE], disengage=0, frontline=1)}
    plain = gank_options({}, enemies)[0]
    tagged = gank_options({}, enemies, {"Zed": ["Assassin"]})[0]
    assert tagged.score < plain.score
    assert any("asesino" in r for r in tagged.reasons)


def test_ranged_vs_ranged_range_difference_counts():
    data = {"Mine": stats(attack_range=650), "Rival": stats(attack_range=550)}
    early = analyze_matchup(profile("Mine", [Role.BOTTOM]), profile("Rival", [Role.BOTTOM]), Role.BOTTOM,
                            data, []).phases[0]
    assert any("Alcance 650 contra 550" in r for r in early.reasons)


def test_bot_lane_combines_carry_and_support():
    enemies = {Role.BOTTOM: profile("ADC", [Role.BOTTOM], disengage=0),
               Role.UTILITY: profile("SUP", [Role.UTILITY], disengage=3)}
    option = gank_options({}, enemies)[0]
    assert option.lane is Role.BOTTOM and option.enemy_ids == ["ADC", "SUP"]
    assert any("desenganche" in r for r in option.reasons)


def test_gank_danger_levels():
    jungler = profile("J", [Role.JUNGLE], early=3, engage=2, cc=2)
    assert gank_danger(profile("Me", [Role.MIDDLE], disengage=0), jungler).level == "alto"
    assert gank_danger(profile("Me", [Role.MIDDLE], disengage=3), jungler).level == "medio"
    assert gank_danger(None, profile("J", [Role.JUNGLE], early=0, engage=0, cc=0)).level == "bajo"
