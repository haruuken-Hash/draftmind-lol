"""Lectura y escritura del perfil del usuario.

El resto de la aplicación solo ve ``UserProfile`` (Pydantic); este módulo es
el único que conoce la tabla ``user_profile``.
"""

from sqlalchemy.orm import sessionmaker

from draftmind.data.database import UserProfileRow
from draftmind.domain.models import UserProfile

_PROFILE_ID = 1


class ProfileRepository:
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def get(self) -> UserProfile:
        with self._session_factory() as session:
            row = session.get(UserProfileRow, _PROFILE_ID)
            if row is None:
                return UserProfile()
            return UserProfile(
                favorite_champions=row.favorite_champions or [],
                main_roles=row.main_roles or [],
                experience=row.experience,
                learning_goals=row.learning_goals or "",
            )

    def save(self, profile: UserProfile) -> None:
        # mode="json" convierte los enums en texto para la columna JSON.
        data = profile.model_dump(mode="json")
        with self._session_factory() as session:
            row = session.get(UserProfileRow, _PROFILE_ID) or UserProfileRow(id=_PROFILE_ID)
            row.favorite_champions = data["favorite_champions"]
            row.main_roles = data["main_roles"]
            row.experience = data["experience"]
            row.learning_goals = data["learning_goals"]
            session.add(row)
            session.commit()
