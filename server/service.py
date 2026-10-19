"""Game logic: the server keeps its own python-chess board and validates every move."""

from __future__ import annotations

import chess
import chess.pgn
from sqlalchemy.orm import Session

from server.db import Game, Move
from server.schemas import GameDetail, GameOut, MoveOut


class MoveRejected(Exception):
    """The edge sent a move the server cannot accept (illegal, gap, or conflicting)."""


def board_for(game: Game) -> chess.Board:
    board = chess.Board(game.start_fen) if game.start_fen else chess.Board()
    for move in game.moves:
        board.push_uci(move.uci)
    return board


def result_of(board: chess.Board) -> str:
    return board.result(claim_draw=False) if board.is_game_over() else "*"


def apply_move(db: Session, game: Game, ply: int, uci: str) -> Move | None:
    """Append a move. Returns None for an exact duplicate (safe edge retry after reconnect)."""
    moves = game.moves
    if ply <= len(moves):
        if moves[ply - 1].uci == uci:
            return None
        raise MoveRejected(f"ply {ply} already holds {moves[ply - 1].uci}, not {uci}")
    if ply != len(moves) + 1:
        raise MoveRejected(f"expected ply {len(moves) + 1}, got {ply}")
    board = board_for(game)
    move = chess.Move.from_uci(uci)
    if move not in board.legal_moves:
        raise MoveRejected(f"illegal move {uci} in {board.fen()}")
    san = board.san(move)
    board.push(move)
    row = Move(game_id=game.id, ply=ply, uci=uci, san=san, fen=board.fen())
    game.moves.append(row)
    game.result = result_of(board)
    db.commit()
    return row


def undo_last(db: Session, game: Game) -> bool:
    if not game.moves:
        return False
    game.moves.pop()  # delete-orphan removes the row
    game.result = "*"
    db.commit()
    return True


def reset_game(db: Session, game: Game, fen: str | None = None) -> None:
    game.moves.clear()
    game.start_fen = fen if fen and fen != chess.STARTING_FEN else None
    game.result = "*"
    db.commit()


def set_result(db: Session, game: Game, result: str) -> None:
    game.result = result
    db.commit()


def game_out(game: Game) -> GameOut:
    board = board_for(game)
    return GameOut(
        id=game.id,
        event=game.event,
        white=game.white,
        black=game.black,
        result=game.result,  # type: ignore[arg-type]
        start_fen=game.start_fen,
        ply=len(game.moves),
        fen=board.fen(),
        created_at=game.created_at,
        updated_at=game.updated_at,
    )


def game_detail(game: Game) -> GameDetail:
    base = game_out(game)
    moves = [MoveOut.model_validate(m) for m in game.moves]
    return GameDetail(**base.model_dump(), moves=moves)


def to_pgn(game: Game) -> str:
    board = board_for(game)
    pgn = chess.pgn.Game.from_board(board)
    pgn.headers["Event"] = game.event
    pgn.headers["Date"] = game.created_at.strftime("%Y.%m.%d")
    pgn.headers["White"] = game.white
    pgn.headers["Black"] = game.black
    pgn.headers["Result"] = game.result
    return str(pgn) + "\n"
