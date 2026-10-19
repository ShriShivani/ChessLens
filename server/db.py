"""SQLAlchemy models and engine setup (SQLite by default, Postgres-compatible)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.pool import StaticPool


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Game(Base):
    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    event: Mapped[str] = mapped_column(String(120), default="ChessLens")
    white: Mapped[str] = mapped_column(String(80), default="?")
    black: Mapped[str] = mapped_column(String(80), default="?")
    start_fen: Mapped[str | None] = mapped_column(String(100), nullable=True)
    result: Mapped[str] = mapped_column(String(8), default="*")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    moves: Mapped[list[Move]] = relationship(
        back_populates="game", order_by="Move.ply", cascade="all, delete-orphan"
    )


class Move(Base):
    __tablename__ = "moves"
    __table_args__ = (UniqueConstraint("game_id", "ply"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    ply: Mapped[int] = mapped_column(Integer)
    uci: Mapped[str] = mapped_column(String(8))
    san: Mapped[str] = mapped_column(String(16))
    fen: Mapped[str] = mapped_column(String(100))  # position after the move
    game: Mapped[Game] = relationship(back_populates="moves")


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool  # one shared in-memory database
        return create_engine(url, **kwargs)
    return create_engine(url, pool_pre_ping=True)


def make_sessionmaker(engine: Engine) -> sessionmaker:
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)
