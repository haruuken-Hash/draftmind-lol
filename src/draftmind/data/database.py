"""Base de datos SQLite con SQLAlchemy 2.x.

Las tablas se describen como clases (ORM). ``init_database`` crea las que
falten; en etapas posteriores se añadirán tablas de caché y partidas.
"""

from datetime import datetime
from pathlib import Path

from sqlalchemy import JSON, DateTime, Engine, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class UserProfileRow(Base):
    """Perfil del usuario. Solo existe una fila (id = 1)."""

    __tablename__ = "user_profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    favorite_champions: Mapped[list] = mapped_column(JSON, default=list)
    main_roles: Mapped[list] = mapped_column(JSON, default=list)
    experience: Mapped[str] = mapped_column(String(32), default="sin_definir")
    learning_goals: Mapped[str] = mapped_column(Text, default="")


class MatchRow(Base):
    """Partida tal como llegó de la Riot API (JSON). Una partida terminada no
    cambia, así que nunca se vuelve a pedir."""

    __tablename__ = "match_cache"

    match_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    platform: Mapped[str] = mapped_column(String(8))
    raw_json: Mapped[str] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TimelineRow(Base):
    """Timeline de una partida (match-v5). Tampoco cambia: se pide una sola vez."""

    __tablename__ = "timeline_cache"

    match_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    raw_json: Mapped[str] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AccountRow(Base):
    """Cuenta de Riot vinculada (Riot ID -> PUUID). Solo se guarda una."""

    __tablename__ = "riot_account"

    id: Mapped[int] = mapped_column(primary_key=True)
    puuid: Mapped[str] = mapped_column(String(100))
    game_name: Mapped[str] = mapped_column(String(64))
    tag_line: Mapped[str] = mapped_column(String(16))
    platform: Mapped[str] = mapped_column(String(8))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProfileOverrideRow(Base):
    """Perfil de campeón revisado por el usuario (JSON de ChampionProfile)."""

    __tablename__ = "champion_profile_override"

    champion_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)


class AppSettingRow(Base):
    """Preferencias de la aplicación como pares clave-valor."""

    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class ResearchSourceRow(Base):
    """Fuente de investigación registrada por el usuario."""

    __tablename__ = "research_source"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(32))
    published_on: Mapped[str] = mapped_column(String(32), default="")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    patch: Mapped[str] = mapped_column(String(16), default="")
    claim: Mapped[str] = mapped_column(Text, default="")
    verification: Mapped[str] = mapped_column(String(32), default="sin_verificar")
    notes: Mapped[str] = mapped_column(Text, default="")


def create_db_engine(db_path: Path | None) -> Engine:
    """``db_path=None`` crea una base de datos en memoria (útil en pruebas)."""
    if db_path is None:
        # StaticPool: todas las sesiones comparten la misma conexión en memoria.
        return create_engine("sqlite:///:memory:", poolclass=StaticPool)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}")


def init_database(engine: Engine) -> sessionmaker:
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
