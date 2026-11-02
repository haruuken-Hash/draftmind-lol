"""Fuentes de investigación guardadas por el usuario."""

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from draftmind.data.database import ResearchSourceRow
from draftmind.domain.models import ResearchSource


class ResearchRepository:
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def list(self) -> list[ResearchSource]:
        with self._session_factory() as session:
            rows = session.scalars(select(ResearchSourceRow).order_by(ResearchSourceRow.retrieved_at.desc())).all()
            return [self._to_model(r) for r in rows]

    def save(self, source: ResearchSource) -> ResearchSource:
        data = source.model_dump(mode="json", exclude={"id", "retrieved_at"})
        with self._session_factory() as session:
            row = session.get(ResearchSourceRow, source.id) if source.id else None
            if row is None:
                row = ResearchSourceRow(retrieved_at=source.retrieved_at)
                session.add(row)
            for key, value in data.items():
                setattr(row, key, value)
            session.commit()
            return self._to_model(row)

    def delete(self, source_id: int) -> None:
        with self._session_factory() as session:
            row = session.get(ResearchSourceRow, source_id)
            if row is not None:
                session.delete(row)
                session.commit()

    @staticmethod
    def _to_model(row: ResearchSourceRow) -> ResearchSource:
        return ResearchSource(
            id=row.id, url=row.url, title=row.title, source_type=row.source_type,
            published_on=row.published_on, retrieved_at=row.retrieved_at, patch=row.patch,
            claim=row.claim, verification=row.verification, notes=row.notes,
        )
