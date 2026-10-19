"""Pydantic models for REST bodies, REST responses and WebSocket messages."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

import chess
from pydantic import BaseModel, ConfigDict, Field, field_validator

Result = Literal["*", "1-0", "0-1", "1/2-1/2"]
UCI_PATTERN = r"^[a-h][1-8][a-h][1-8][qrbn]?$"


def _check_fen(fen: str) -> str:
    try:
        chess.Board(fen)
    except ValueError as exc:
        raise ValueError(f"invalid FEN: {exc}") from exc
    return fen


class GameCreate(BaseModel):
    event: str = Field("ChessLens", max_length=120)
    white: str = Field("?", max_length=80)
    black: str = Field("?", max_length=80)
    start_fen: str | None = Field(None, max_length=100)

    @field_validator("start_fen")
    @classmethod
    def valid_fen(cls, v: str | None) -> str | None:
        return _check_fen(v) if v else None


class MoveOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ply: int
    san: str
    uci: str
    fen: str


class GameOut(BaseModel):
    id: str
    event: str
    white: str
    black: str
    result: Result
    start_fen: str | None
    ply: int
    fen: str
    created_at: datetime
    updated_at: datetime


class GameDetail(GameOut):
    moves: list[MoveOut]


# ---- edge -> server messages (discriminated by "type") ----------------------------
class MoveMsg(BaseModel):
    type: Literal["move"]
    ply: int = Field(ge=1)
    uci: str = Field(pattern=UCI_PATTERN)


class UndoMsg(BaseModel):
    type: Literal["undo"]


class ResetMsg(BaseModel):
    type: Literal["reset"]


class SetFenMsg(BaseModel):
    type: Literal["set_fen"]
    fen: str = Field(max_length=100)

    @field_validator("fen")
    @classmethod
    def valid_fen(cls, v: str) -> str:
        return _check_fen(v)


class ResultMsg(BaseModel):
    type: Literal["result"]
    result: Result


IngestMessage = Annotated[
    MoveMsg | UndoMsg | ResetMsg | SetFenMsg | ResultMsg, Field(discriminator="type")
]
