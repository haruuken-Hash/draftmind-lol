"""Caché local de partidas y cuenta vinculada."""

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from draftmind.data.database import AccountRow, MatchRow, TimelineRow

_ACCOUNT_ID = 1


@dataclass(frozen=True)
class LinkedAccount:
    puuid: str
    game_name: str
    tag_line: str
    platform: str
    retrieved_at: datetime

    @property
    def riot_id(self) -> str:
        return f"{self.game_name}#{self.tag_line}"


class MatchRepository:
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def has_match(self, match_id: str) -> bool:
        with self._session_factory() as session:
            return session.get(MatchRow, match_id) is not None

    def save_match(self, match_id: str, platform: str, raw: dict) -> None:
        with self._session_factory() as session:
            session.merge(MatchRow(
                match_id=match_id, platform=platform, raw_json=json.dumps(raw),
                retrieved_at=datetime.now(timezone.utc),
            ))
            session.commit()

    def all_matches(self) -> list[tuple[str, dict]]:
        """(plataforma, JSON) de todas las partidas guardadas."""
        with self._session_factory() as session:
            rows = session.scalars(select(MatchRow)).all()
            return [(r.platform, json.loads(r.raw_json)) for r in rows]

    def get_match(self, match_id: str) -> tuple[str, dict] | None:
        with self._session_factory() as session:
            row = session.get(MatchRow, match_id)
            return (row.platform, json.loads(row.raw_json)) if row else None

    def get_timeline(self, match_id: str) -> dict | None:
        with self._session_factory() as session:
            row = session.get(TimelineRow, match_id)
            return json.loads(row.raw_json) if row else None

    def save_timeline(self, match_id: str, raw: dict) -> None:
        with self._session_factory() as session:
            session.merge(TimelineRow(match_id=match_id, raw_json=json.dumps(raw),
                                      retrieved_at=datetime.now(timezone.utc)))
            session.commit()

    def count(self) -> int:
        with self._session_factory() as session:
            return len(session.scalars(select(MatchRow.match_id)).all())

    def clear_matches(self) -> None:
        with self._session_factory() as session:
            session.query(MatchRow).delete()
            session.query(TimelineRow).delete()
            session.commit()

    def get_account(self) -> LinkedAccount | None:
        with self._session_factory() as session:
            row = session.get(AccountRow, _ACCOUNT_ID)
            if row is None:
                return None
            return LinkedAccount(row.puuid, row.game_name, row.tag_line, row.platform, row.retrieved_at)

    def save_account(self, account: LinkedAccount) -> None:
        with self._session_factory() as session:
            session.merge(AccountRow(
                id=_ACCOUNT_ID, puuid=account.puuid, game_name=account.game_name,
                tag_line=account.tag_line, platform=account.platform, retrieved_at=account.retrieved_at,
            ))
            session.commit()
