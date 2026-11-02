"""Perfiles: estimación automática, prioridad de fuentes y revisiones del usuario."""

from draftmind.analysis.draft_analyzer import DraftAnalyzer
from draftmind.analysis.profile_estimator import can_estimate, estimate_profile
from draftmind.data.database import create_db_engine, init_database
from draftmind.data.repositories.champion_profile_repository import ChampionProfileRepository
from draftmind.domain.enums import DamageType, EvidenceKind, ProfileOrigin, Role
from draftmind.domain.models import ChampionCatalog, ChampionInfo, DataSource, DraftPick, DraftState
from draftmind.services.profile_service import build_profiles

# Valores oficiales reales de Data Dragon 16.21.1 (champion.json: tags, info, stats.attackrange).
LEONA = ChampionInfo(id="Leona", name="Leona", tags=["Tank", "Support"], attack=4, defense=8, magic=3,
                     difficulty=4, attack_range=125)
JINX = ChampionInfo(id="Jinx", name="Jinx", tags=["Marksman"], attack=9, defense=2, magic=4,
                    difficulty=6, attack_range=525)
YORICK = ChampionInfo(id="Yorick", name="Yorick", tags=["Fighter", "Tank"], attack=6, defense=6, magic=4,
                      difficulty=6, attack_range=175)
VEIGAR = ChampionInfo(id="Veigar", name="Veigar", tags=["Mage"], attack=2, defense=2, magic=10,
                      difficulty=7, attack_range=550)


def catalog(*infos):
    return ChampionCatalog(source=DataSource(name="test", kind=EvidenceKind.OFFICIAL), version="16.21.1",
                           language="es_MX", champions=list(infos))


def test_estimates_follow_class_and_official_values():
    leona = estimate_profile(LEONA)
    assert leona.origin is ProfileOrigin.ESTIMATED
    assert leona.roles == [Role.TOP, Role.UTILITY]   # Clase Tank + Support.
    assert leona.frontline == 3 and leona.engage == 3 and leona.difficulty == 1
    jinx = estimate_profile(JINX)
    assert jinx.roles == [Role.BOTTOM] and jinx.damage_type is DamageType.PHYSICAL
    assert jinx.frontline == 0 and jinx.resource_dependence == 3
    veigar = estimate_profile(VEIGAR)
    assert veigar.damage_type is DamageType.MAGIC and veigar.roles == [Role.MIDDLE]


def test_estimates_stay_in_valid_ranges():
    for info in (LEONA, JINX, YORICK, VEIGAR):
        p = estimate_profile(info)  # Pydantic rechazaría valores fuera de 0-3 / 1-3.
        assert 1 <= p.difficulty <= 3


def test_cannot_estimate_without_official_data():
    assert not can_estimate(ChampionInfo(id="X", name="X"))


def test_priority_estimated_editorial_user(dataset):
    editorial_leona = next(p for p in dataset.champions if p.id == "Leona")
    user_jinx = estimate_profile(JINX).model_copy(update={"frontline": 1})
    profiles = {p.id: p for p in build_profiles(catalog(LEONA, JINX, YORICK), [editorial_leona], [user_jinx])}
    assert profiles["Yorick"].origin is ProfileOrigin.ESTIMATED
    assert profiles["Leona"].origin is ProfileOrigin.EDITORIAL
    assert profiles["Jinx"].origin is ProfileOrigin.USER and profiles["Jinx"].frontline == 1


def _raw_match(players, duration=1800):
    return {"info": {"gameDuration": duration, "gameEndTimestamp": 1,
                     "participants": [{"championName": c, "teamPosition": p} for c, p in players]}}


def test_observed_positions_count_all_players_and_skip_remakes():
    from draftmind.services.profile_service import observed_positions

    matches = [
        _raw_match([("Yorick", "JUNGLE"), ("Jinx", "BOTTOM"), ("Leona", "")]),
        _raw_match([("Yorick", "JUNGLE"), ("Jinx", "BOTTOM")]),
        _raw_match([("Yorick", "TOP")], duration=200),  # Posible remake: no cuenta.
    ]
    positions = observed_positions(matches)
    assert positions["Yorick"] == {Role.JUNGLE: 2}
    assert "Leona" not in positions  # Posición vacía.


def test_observed_positions_replace_estimated_roles_only(dataset):
    from collections import Counter

    editorial_leona = next(p for p in dataset.champions if p.id == "Leona")
    positions = {
        "Yorick": Counter({Role.JUNGLE: 6, Role.TOP: 3, Role.MIDDLE: 1}),  # Medio: 10 %, no llega.
        "Jinx": Counter({Role.UTILITY: 1}),                                # Una sola vez: no basta.
        "Leona": Counter({Role.MIDDLE: 9}),                                # Editorial: no se toca.
    }
    profiles = {p.id: p for p in build_profiles(catalog(YORICK, JINX, LEONA), [editorial_leona], [], positions)}
    assert profiles["Yorick"].roles == [Role.JUNGLE, Role.TOP] and profiles["Yorick"].roles_observed == 10
    assert profiles["Jinx"].roles == [Role.BOTTOM] and profiles["Jinx"].roles_observed == 0
    assert profiles["Leona"].roles == editorial_leona.roles


def test_user_overrides_persist():
    repo = ChampionProfileRepository(init_database(create_db_engine(None)))
    saved = repo.save(estimate_profile(YORICK).model_copy(update={"engage": 2}))
    assert saved.origin is ProfileOrigin.USER
    assert repo.all()[0].engage == 2 and repo.all()[0].origin is ProfileOrigin.USER
    repo.delete("Yorick")
    assert repo.all() == []


def test_estimated_profiles_weigh_less_and_are_flagged(dataset):
    editorial = next(p for p in dataset.champions if p.id == "Malphite")
    estimated = editorial.model_copy(update={"origin": ProfileOrigin.ESTIMATED, "id": "MalphiteBis",
                                             "name": "Malphite estimado"})
    analyzer = DraftAnalyzer([editorial, estimated] + [p for p in dataset.champions if p.id != "Malphite"],
                             dataset.source)
    draft = DraftState(my_role=Role.TOP, allies=[DraftPick(champion_id=i) for i in ("Zed", "Jinx", "Janna")])
    real = analyzer.analyze_candidate(draft, "Malphite")
    copy = analyzer.analyze_candidate(draft, "MalphiteBis")
    assert real.score > copy.score > 50  # Mismos atributos, pero el estimado pesa menos.
    assert any("estimados automáticamente" in w for w in copy.confidence.warnings)
    assert not any("estimados automáticamente" in w for w in real.confidence.warnings)
