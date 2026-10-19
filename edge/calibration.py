"""Board calibration: four clicked corners -> top-down 800x800 warp."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import chess
import cv2
import numpy as np

BOARD_SIZE = 800
SQUARE_SIZE = BOARD_SIZE // 8

# Which edge of the camera image White's first rank is nearest to.
WHITE_SIDES = ("bottom", "left", "top", "right")


@dataclass(frozen=True)
class Calibration:
    """Corners are clicked clockwise starting at the image's top-left board corner."""

    corners: tuple[tuple[float, float], ...]
    white_side: str = "bottom"

    def __post_init__(self) -> None:
        if len(self.corners) != 4:
            raise ValueError("exactly 4 corners are required")
        if self.white_side not in WHITE_SIDES:
            raise ValueError(f"white_side must be one of {WHITE_SIDES}")

    def flipped(self) -> Calibration:
        opposite = {"bottom": "top", "top": "bottom", "left": "right", "right": "left"}
        return Calibration(self.corners, opposite[self.white_side])

    def matrix(self) -> np.ndarray:
        """Perspective transform from camera image to a board with White at the bottom."""
        s = float(BOARD_SIZE)
        dst = [(0.0, 0.0), (s, 0.0), (s, s), (0.0, s)]  # TL, TR, BR, BL
        # Rotate the destination so White's edge lands at the bottom of the warp.
        shift = {"bottom": 0, "left": 3, "top": 2, "right": 1}[self.white_side]
        dst = dst[shift:] + dst[:shift]
        return cv2.getPerspectiveTransform(
            np.array(self.corners, dtype=np.float32), np.array(dst, dtype=np.float32)
        )

    def warp(self, frame: np.ndarray) -> np.ndarray:
        return cv2.warpPerspective(frame, self.matrix(), (BOARD_SIZE, BOARD_SIZE))

    def save(self, path: str | Path) -> None:
        data = {"corners": [list(c) for c in self.corners], "white_side": self.white_side}
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> Calibration:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        corners = tuple((float(x), float(y)) for x, y in data["corners"])
        return cls(corners, data.get("white_side", "bottom"))


def square_bounds(square: chess.Square) -> tuple[int, int, int, int]:
    """Pixel box (y0, y1, x0, x1) of a square in the warped image (White at bottom)."""
    file = chess.square_file(square)
    row = 7 - chess.square_rank(square)
    return row * SQUARE_SIZE, (row + 1) * SQUARE_SIZE, file * SQUARE_SIZE, (file + 1) * SQUARE_SIZE
