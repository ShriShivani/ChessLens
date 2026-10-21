"""Use a per-square classifier as a check on the move tracker (never as its replacement).

Three uses, from the ML plan (docs/ML_PLAN.md section 8):
  1. verification   : tracker board vs classifier occupancy -> flag a possible desync
  2. move choice    : legal moves whose result the classifier finds unlikely score lower
  3. recovery       : decode a whole position, repair it with chess rules, propose a FEN

All functions take `probs`, a (64, 13) array of class probabilities indexed by chess square
(see ml.common for the class layout), so they work with any model and are easy to test.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import chess
import numpy as np

from edge.detector import expected_squares
from ml.common import NUM_CLASSES, class_of, piece_of


class Classifier(Protocol):
    def predict(self, warped: np.ndarray) -> np.ndarray:
        """(64, 13) class probabilities for a warped 800x800 board."""
        ...


def occupancy_probs(probs: np.ndarray) -> np.ndarray:
    """(64, 3): probability of empty / white / black on each square."""
    return np.stack([probs[:, 0], probs[:, 1:7].sum(1), probs[:, 7:13].sum(1)], axis=1)


def board_occupancy(board: chess.Board) -> np.ndarray:
    """(64,) 0 empty, 1 white, 2 black."""
    out = np.zeros(64, dtype=np.int64)
    for sq, piece in board.piece_map().items():
        out[sq] = 1 if piece.color == chess.WHITE else 2
    return out


def occupancy_mismatches(board: chess.Board, probs: np.ndarray, min_confidence: float = 0.6):
    """Squares where the classifier confidently disagrees with the tracker's board."""
    occ = occupancy_probs(probs)
    predicted, conf = occ.argmax(1), occ.max(1)
    expected = board_occupancy(board)
    return [
        sq for sq in chess.SQUARES if predicted[sq] != expected[sq] and conf[sq] >= min_confidence
    ]


def move_agreement(board: chess.Board, move: chess.Move, occ: np.ndarray) -> float:
    """Mean classifier probability of the occupancy a move would leave on the squares it changes."""
    after = board.copy(stack=False)
    after.push(move)
    expected = board_occupancy(after)
    touched = expected_squares(board, move)
    return float(np.mean([occ[sq, expected[sq]] for sq in touched]))


def make_prior(
    board: chess.Board, moves: list[chess.Move], probs: np.ndarray, weight: float
) -> Callable[[chess.Move], float]:
    """Score bonus (<= 0) per move: how much less the classifier likes it than its favourite.

    Never raises a score, so it cannot turn a weak move into a confident one; it only widens
    the margin between the move the classifier supports and the alternatives.
    """
    occ = occupancy_probs(probs)
    agreement = {m: move_agreement(board, m, occ) for m in moves}
    best = max(agreement.values(), default=0.0)
    return lambda m: weight * (agreement.get(m, best) - best)


def consistency_errors(pieces: dict[int, chess.Piece]) -> list[str]:
    """Rule violations in a set of pieces; empty list means a plausible position."""
    errors: list[str] = []
    for color, name in ((chess.WHITE, "white"), (chess.BLACK, "black")):
        mine = [(sq, p) for sq, p in pieces.items() if p.color == color]
        count = {t: sum(1 for _, p in mine if p.piece_type == t) for t in range(1, 7)}
        if count[chess.KING] != 1:
            errors.append(f"{name} has {count[chess.KING]} kings")
        if count[chess.PAWN] > 8:
            errors.append(f"{name} has {count[chess.PAWN]} pawns")
        if any(p.piece_type == chess.PAWN and chess.square_rank(sq) in (0, 7) for sq, p in mine):
            errors.append(f"{name} pawn on the first or last rank")
        if len(mine) > 16:
            errors.append(f"{name} has {len(mine)} pieces")
        extra = sum(
            max(0, count[t] - start)
            for t, start in (
                (chess.QUEEN, 1),
                (chess.ROOK, 2),
                (chess.BISHOP, 2),
                (chess.KNIGHT, 2),
            )
        )
        if count[chess.PAWN] + extra > 8:
            errors.append(f"{name} has more promoted pieces than missing pawns allow")
    return errors


def _next_best(row: np.ndarray, banned: set[int], color: bool | None) -> int:
    """Best class for a square that is not in `banned` (keeping colour if `color` is given)."""
    order = np.argsort(-row)
    for cls in order:
        piece = piece_of(int(cls))
        if int(cls) in banned:
            continue
        if color is not None and piece is not None and piece.color != color:
            continue
        return int(cls)
    return 0


def decode_position(probs: np.ndarray, turn: bool = chess.WHITE) -> tuple[chess.Board, list[str]]:
    """Most likely position, repaired with chess rules where possible.

    Returns (board, remaining_errors). The board has no castling rights or en passant square;
    the operator confirms or edits the FEN before it is used.
    """
    if probs.shape != (64, NUM_CLASSES):
        raise ValueError(f"expected (64, {NUM_CLASSES}) probabilities")
    cls = probs.argmax(1).astype(int)
    pawn_ids = {class_of(chess.Piece(chess.PAWN, c)) for c in (chess.WHITE, chess.BLACK)}

    for sq in chess.SQUARES:  # pawns cannot stand on the first or last rank
        if cls[sq] in pawn_ids and chess.square_rank(sq) in (0, 7):
            piece = piece_of(int(cls[sq]))
            cls[sq] = _next_best(probs[sq], pawn_ids, piece.color if piece else None)

    for color in (chess.WHITE, chess.BLACK):
        king = class_of(chess.Piece(chess.KING, color))
        spots = [sq for sq in chess.SQUARES if cls[sq] == king]
        if len(spots) > 1:  # keep the most king-like square, demote the rest
            spots.sort(key=lambda s: -probs[s, king])
            for sq in spots[1:]:
                cls[sq] = _next_best(probs[sq], {king}, color)
        elif not spots:  # promote the most king-like square among this colour's pieces
            mine = [
                sq
                for sq in chess.SQUARES
                if cls[sq] != 0 and (piece_of(int(cls[sq])).color == color)
            ]
            if mine:
                cls[max(mine, key=lambda s: probs[s, king])] = king
        pawn = class_of(chess.Piece(chess.PAWN, color))
        pawns = sorted(
            (sq for sq in chess.SQUARES if cls[sq] == pawn), key=lambda s: probs[s, pawn]
        )
        for sq in pawns[: max(0, len(pawns) - 8)]:  # demote the least pawn-like extras
            cls[sq] = _next_best(probs[sq], {pawn}, color)

    board = chess.Board(None)
    for sq in chess.SQUARES:
        piece = piece_of(int(cls[sq]))
        if piece:
            board.set_piece_at(sq, piece)
    board.turn = turn
    return board, consistency_errors(board.piece_map())
