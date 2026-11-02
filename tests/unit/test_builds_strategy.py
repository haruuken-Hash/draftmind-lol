from pathlib import Path

import httpx
import pytest

from draftmind.analysis.build_analyzer import build_advice, item_needs, rune_advice, spell_advice
from draftmind.analysis.composition_analyzer import analyze_team
from draftmind.analysis.strategy_analyzer import analyze_strategy
from draftmind.domain.enums import EvidenceKind, Role
from draftmind.domain.models import MatchSummary
from draftmind.integrations.data_dragon import DataDragonClient
from tests.unit.test_data_dragon import FakeDDragon


@pytest.fixture
def game_data(tmp_path):
    http = httpx.Client(transport=httpx.MockTransport(FakeDDragon()))
    return DataDragonClient(tmp_path, http=http).game_data("16.21.1", "es_MX")


@pytest.fixture
def profiles(dataset):
    return {c.id: c for c in dataset.champions}


def team(profiles, *ids):
    return analyze_team([profiles[i] for i in ids])


def test_physical_enemies_suggest_armor_items(profiles, game_data):
    enemies = team(profiles, "Zed", "Darius", "Jinx")
    needs = item_needs(profiles["Malphite"], enemies, game_data)
    armor = next(n for n in needs if n.title == "Armadura")
    assert armor.kind is EvidenceKind.INFERENCE
    assert {i.name for i in armor.items} >= {"Malla de Espinas"}
    assert all("Armor" in i.tags for i in armor.items)


def test_fighters_prefer_resistance_with_damage(profiles, game_data):
    from draftmind.domain.models import ItemInfo

    hybrid = ItemInfo(id="6333", name="Danza de la Muerte", total_gold=3300, tags=["Armor", "Damage"])
    data = game_data.model_copy(update={"items": game_data.items + [hybrid]})
    enemies = team(profiles, "Zed", "Darius", "Jinx")
    fighter = profiles["Darius"]  # Primera línea 2: luchador, no tanque puro.
    armor = next(n for n in item_needs(fighter, enemies, data, Role.TOP) if n.title == "Armadura")
    assert armor.items[0].name == "Danza de la Muerte"
    tank = next(n for n in item_needs(profiles["Malphite"], enemies, data, Role.TOP) if n.title == "Armadura")
    assert "Danza de la Muerte" not in {i.name for i in tank.items}


def test_ally_items_only_for_support(profiles, game_data):
    enemies = team(profiles, "Zed", "Darius", "Jinx")
    top = next(n for n in item_needs(profiles["Malphite"], enemies, game_data, Role.TOP) if n.title == "Armadura")
    support = next(n for n in item_needs(profiles["Leona"], enemies, game_data, Role.UTILITY) if n.title == "Armadura")
    assert "Relicario de los Solari de Hierro" not in {i.name for i in top.items}
    assert "Relicario de los Solari de Hierro" in {i.name for i in support.items}


def test_heavy_cc_suggests_tenacity(profiles, game_data):
    enemies = team(profiles, "Leona", "Amumu", "Malphite")
    needs = item_needs(profiles["Jinx"], enemies, game_data)
    tenacity = next(n for n in needs if n.title == "Tenacidad")
    assert [i.name for i in tenacity.items] == ["Botas de Mercurio"]


def test_no_enemies_no_needs(profiles, game_data):
    assert item_needs(profiles["Jinx"], analyze_team([]), game_data) == []


def test_runes_use_official_paths_and_are_educational(profiles, game_data):
    advice = rune_advice(profiles["Malphite"], game_data)
    assert advice[0].path.key == "Resolve"
    assert all(a.kind is EvidenceKind.EDUCATIONAL for a in advice)
    assert "No es una estadística" in advice[0].reason


def test_spells_by_role_come_from_data_dragon(game_data):
    spells = spell_advice(Role.JUNGLE, analyze_team([]), game_data)
    assert [s.name for s in spells] == ["Destello", "Aplastar"]


def test_frequent_items_from_personal_matches_never_invent_rates(profiles, game_data):
    matches = [
        MatchSummary(match_id=str(i), platform="LA1", puuid="P", champion_id="Malphite", win=i % 2 == 0,
                     items=[3075, 3047, 3340], keystone_id=8437)
        for i in range(4)
    ]
    advice = build_advice("Malphite", profiles["Malphite"], Role.TOP, analyze_team([]), game_data, matches)
    assert {f.name for f in advice.frequent_items} == {"Malla de Espinas", "Punteras de Acero Revestidas"}
    assert advice.frequent_items[0].games == 4 and advice.frequent_items[0].wins == 2
    assert advice.frequent_keystones == [("Garras del Inmortal", 4, 2)]
    assert any("no bastan" in n for n in advice.notes)


def test_strategy_separates_facts_and_hypotheses(profiles):
    ally = team(profiles, "Malphite", "Amumu", "Orianna", "Jinx", "Leona")
    enemy = team(profiles, "Kayle", "MasterYi", "Kassadin", "Vayne", "Janna")
    report = analyze_strategy(ally, enemy)
    assert report.enough_data
    assert any("Reparto de daño" in f for f in report.ally.facts)
    assert any("iniciación" in w for w in report.ally.win_conditions)
    assert "más fuerte al principio" in report.power_window and report.power_window.startswith("Hipótesis")
    assert any("Llegar a la fase tardía" in w for w in report.enemy.win_conditions)
    assert len(report.questions) >= 4


def test_strategy_with_empty_draft():
    report = analyze_strategy(analyze_team([]), analyze_team([]))
    assert not report.enough_data
    assert "Hacen falta" in report.power_window
