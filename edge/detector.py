"""Move detection by tracking: score every legal move against measured square change."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import chess
import cv2
import numpy as np

from edge.calibration import SQUARE_SIZE, square_bounds

# Inner fraction of each square that is compared (ignores grid lines and bleed).
INNER = 0.8


@dataclass(frozen=True)
class DetectorConfig:
    full_change: float = 40.0  # mean gray-level difference that counts as a fully changed square
    changed_threshold: float = 0.3  # normalised change above which a square counts as changed
    leak_penalty: float = 0.4  # weight of change on squares the move does NOT touch
    noise_floor: float = 0.1  # per-square change below this is sensor noise, not leakage
    min_confidence: float = 0.55
    min_margin: float = 0.15
    max_changed_squares: int = 6  # more than this means a hand/lighting event, not a move


@dataclass(frozen=True)
class Candidate:
    move: chess.Move
    score: float


@dataclass(frozen=True)
class Detection:
    """Outcome of comparing two stable frames."""

    status: str  # "nochange" | "occluded" | "move" | "uncertain"
    move: chess.Move | None = None
    confidence: float = 0.0
    margin: float = 0.0
    candidates: tuple[Candidate, ...] = field(default_factory=tuple)


def _gray(warped: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY) if warped.ndim == 3 else warped
    return gray.astype(np.float32)


def _match_exposure(ref: np.ndarray, cur: np.ndarray) -> np.ndarray:
    """Map `cur` onto `ref`'s exposure with a robust gain+offset fit.

    Pixels that actually changed (pieces moving) are trimmed from the fit so they do not
    drag the correction, but global lighting changes are removed.
    """
    x, y = cur[::4, ::4].ravel(), ref[::4, ::4].ravel()
    keep = np.ones_like(x, dtype=bool)
    gain, offset = 1.0, 0.0
    for _ in range(3):
        gain, offset = np.polyfit(x[keep], y[keep], 1)
        resid = np.abs(gain * x + offset - y)
        keep = resid <= np.percentile(resid, 80)
    return cur * gain + offset


def square_changes(prev: np.ndarray, cur: np.ndarray, cfg: DetectorConfig) -> np.ndarray:
    """Normalised change in [0, 1] for each of the 64 squares (index = chess square)."""
    a, b = _gray(prev), _gray(cur)
    b = _match_exposure(a, b)
    diff = np.abs(cv2.GaussianBlur(a, (5, 5), 0) - cv2.GaussianBlur(b, (5, 5), 0))
    margin = int(SQUARE_SIZE * (1 - INNER) / 2)
    out = np.zeros(64, dtype=np.float32)
    for sq in chess.SQUARES:
        y0, y1, x0, x1 = square_bounds(sq)
        patch = diff[y0 + margin : y1 - margin, x0 + margin : x1 - margin]
        out[sq] = patch.mean() / cfg.full_change
    return np.clip(out, 0.0, 1.0)


def expected_squares(board: chess.Board, move: chess.Move) -> frozenset[int]:
    """Squares whose appearance changes when `move` is played."""
    squares = {move.from_square, move.to_square}
    if board.is_en_passant(move):
        squares.add(
            chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square))
        )
    if board.is_castling(move):
        rank = chess.square_rank(move.from_square)
        kingside = chess.square_file(move.to_square) > chess.square_file(move.from_square)
        squares |= {
            chess.square(7 if kingside else 0, rank),
            chess.square(5 if kingside else 3, rank),
        }
    return frozenset(squares)


def candidate_moves(board: chess.Board) -> list[chess.Move]:
    """Legal moves with promotions collapsed to queen (piece type is not visible)."""
    return [m for m in board.legal_moves if m.promotion in (None, chess.QUEEN)]


def score_move(
    board: chess.Board, move: chess.Move, changes: np.ndarray, cfg: DetectorConfig
) -> float:
    touched = expected_squares(board, move)
    inside = float(np.mean([changes[s] for s in touched]))
    leak = float(
        sum(changes[s] for s in chess.SQUARES if s not in touched and changes[s] > cfg.noise_floor)
    )
    return inside - cfg.leak_penalty * leak


def detect_move(
    board: chess.Board,
    prev: np.ndarray,
    cur: np.ndarray,
    cfg: DetectorConfig | None = None,
    prior: Callable[[chess.Move], float] | None = None,
) -> Detection:
    """Decide which legal move (if any) turned `prev` into `cur`.

    `prior` optionally adds a per-move score adjustment (for example from a classifier).
    """
    cfg = cfg or DetectorConfig()
    changes = square_changes(prev, cur, cfg)
    n_changed = int(np.sum(changes > cfg.changed_threshold))
    if n_changed == 0:
        return Detection("nochange")
    if n_changed > cfg.max_changed_squares:
        return Detection("occluded")

    scored = sorted(
        (
            Candidate(m, score_move(board, m, changes, cfg) + (prior(m) if prior else 0.0))
            for m in candidate_moves(board)
        ),
        key=lambda c: c.score,
        reverse=True,
    )
    if not scored:
        return Detection("uncertain")
    best = scored[0]
    margin = best.score - scored[1].score if len(scored) > 1 else best.score
    top = tuple(scored[:3])
    if best.score >= cfg.min_confidence and margin >= cfg.min_margin:
        return Detection("move", best.move, best.score, margin, top)
    return Detection("uncertain", None, best.score, margin, top)
