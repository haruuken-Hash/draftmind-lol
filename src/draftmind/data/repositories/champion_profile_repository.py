"""Perfiles de campeón revisados por el usuario."""

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from draftmind.data.database import ProfileOverrideRow
from draftmind.domain.enums import ProfileOrigin
from draftmind.domain.models import ChampionProfile


class ChampionProfileRepository:
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def all(self) -> list[ChampionProfile]:
        with self._session_factory() as session:
            rows = session.scalars(select(ProfileOverrideRow)).all()
            return [ChampionProfile.model_validate(r.data) for r in rows]

    def save(self, profile: ChampionProfile) -> ChampionProfile:
        reviewed = profile.model_copy(update={"origin": ProfileOrigin.USER})
        with self._session_factory() as session:
            session.merge(ProfileOverrideRow(champion_id=reviewed.id, data=reviewed.model_dump(mode="json")))
            session.commit()
        return reviewed

    def delete(self, champion_id: str) -> None:
        with self._session_factory() as session:
            row = session.get(ProfileOverrideRow, champion_id)
            if row is not None:
                session.delete(row)
                session.commit()
