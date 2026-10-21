"""Crop and label definitions shared by training, evaluation and inference.

One crop function is used everywhere. A mismatch between training and inference preprocessing
is a classic silent bug, so nothing else in the repository may cut squares out of a board.
"""

from __future__ import annotations

import chess
import cv2
import numpy as np

from edge.calibration import BOARD_SIZE, SQUARE_SIZE

CROP_PAD = 14  # context kept around each square so overhanging pieces are not cut off
CROP_SIZE = SQUARE_SIZE + 2 * CROP_PAD  # 128 px before resizing
DEFAULT_INPUT = 96  # model input side; 112 is the other size worth trying

# 13 classes: 0 empty, 1-6 white P N B R Q K, 7-12 black P N B R Q K.
PIECE_ORDER = (
    chess.PAWN,
    chess.KNIGHT,
    chess.BISHOP,
    chess.ROOK,
    chess.QUEEN,
    chess.KING,
)
CLASS_NAMES = ["empty"] + [f"{c}{chess.piece_symbol(p).upper()}" for c in "wb" for p in PIECE_ORDER]
OCC_NAMES = ["empty", "white", "black"]
TYPE_NAMES = [chess.piece_name(p) for p in PIECE_ORDER]
NUM_CLASSES = len(CLASS_NAMES)


def square_crops(warped: np.ndarray, size: int = DEFAULT_INPUT) -> np.ndarray:
    """64 RGB crops, shape (64, size, size, 3) uint8, indexed by chess square (a1 = 0).

    `warped` is the 800x800 BGR top-down board with White at the bottom.
    """
    if warped.shape[:2] != (BOARD_SIZE, BOARD_SIZE):
        raise ValueError(f"expected {BOARD_SIZE}x{BOARD_SIZE} warped board, got {warped.shape}")
    padded = cv2.copyMakeBorder(
        warped, CROP_PAD, CROP_PAD, CROP_PAD, CROP_PAD, cv2.BORDER_REPLICATE
    )
    out = np.empty((64, size, size, 3), dtype=np.uint8)
    for sq in chess.SQUARES:
        row, file = 7 - chess.square_rank(sq), chess.square_file(sq)
        y, x = row * SQUARE_SIZE, file * SQUARE_SIZE
        crop = padded[y : y + CROP_SIZE, x : x + CROP_SIZE]
        crop = cv2.resize(crop, (size, size), interpolation=cv2.INTER_AREA)
        out[sq] = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    return out


def class_of(piece: chess.Piece | None) -> int:
    if piece is None:
        return 0
    return 1 + (0 if piece.color == chess.WHITE else 6) + PIECE_ORDER.index(piece.piece_type)


def piece_of(cls: int) -> chess.Piece | None:
    if cls == 0:
        return None
    cls -= 1
    color = chess.WHITE if cls < 6 else chess.BLACK
    return chess.Piece(PIECE_ORDER[cls % 6], color)


def board_labels(board: chess.Board) -> np.ndarray:
    """(64,) int64 class index per square."""
    return np.array([class_of(board.piece_at(sq)) for sq in chess.SQUARES], dtype=np.int64)


def split_label(cls: np.ndarray | int) -> tuple[np.ndarray, np.ndarray]:
    """Class index -> (occupancy 0/1/2, piece type 0-5 or -1 for empty squares)."""
    cls = np.asarray(cls)
    occ = np.where(cls == 0, 0, np.where(cls <= 6, 1, 2))
    typ = np.where(cls == 0, -1, (cls - 1) % 6)
    return occ, typ


def join_probs(occ_p: np.ndarray, typ_p: np.ndarray) -> np.ndarray:
    """Combine head probabilities (N,3) and (N,6) into 13-class probabilities (N,13)."""
    out = np.empty((occ_p.shape[0], NUM_CLASSES), dtype=np.float32)
    out[:, 0] = occ_p[:, 0]
    out[:, 1:7] = occ_p[:, 1:2] * typ_p
    out[:, 7:13] = occ_p[:, 2:3] * typ_p
    return out
