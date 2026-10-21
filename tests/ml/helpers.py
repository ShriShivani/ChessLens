"""Test helpers: probabilities as a classifier would output them."""

from __future__ import annotations

import chess
import numpy as np

from ml.common import NUM_CLASSES, board_labels


def probs_for(board: chess.Board, confidence: float = 0.94) -> np.ndarray:
    """(64, 13) probabilities that put `confidence` on the true class of every square."""
    out = np.full((64, NUM_CLASSES), (1 - confidence) / (NUM_CLASSES - 1), dtype=np.float32)
    out[np.arange(64), board_labels(board)] = confidence
    return out
