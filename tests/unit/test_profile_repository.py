from draftmind.data.database import create_db_engine, init_database
from draftmind.data.repositories.profile_repository import ProfileRepository
from draftmind.domain.enums import ExperienceLevel, Role
from draftmind.domain.models import UserProfile


def test_missing_profile_returns_defaults():
    repo = ProfileRepository(init_database(create_db_engine(None)))
    assert repo.get() == UserProfile()


def test_profile_round_trip_on_disk(tmp_path):
    db = tmp_path / "sub" / "test.db"
    profile = UserProfile(
        favorite_champions=["Ahri", "Leona"],
        main_roles=[Role.MIDDLE, Role.UTILITY],
        experience=ExperienceLevel.INTERMEDIATE,
        learning_goals="Mejorar el control de oleadas",
    )
    ProfileRepository(init_database(create_db_engine(db))).save(profile)

    # Un repositorio nuevo sobre el mismo archivo simula reabrir la aplicación.
    reopened = ProfileRepository(init_database(create_db_engine(db)))
    assert reopened.get() == profile


def test_saving_twice_overwrites():
    repo = ProfileRepository(init_database(create_db_engine(None)))
    repo.save(UserProfile(learning_goals="a"))
    repo.save(UserProfile(learning_goals="b"))
    assert repo.get().learning_goals == "b"
