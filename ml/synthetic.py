"""Synthetic top-down boards for pretraining.

IMPORTANT: these pieces are an invented top-down look (discs with simple per-type marks), not
photographs or models of real pieces. They are useful to exercise the pipeline and to
pretrain on shape and colour cues. A classifier that does well on them has shown NOTHING about
real boards. Real crops are needed for any claim about real accuracy.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import chess
import cv2
import numpy as np

from edge.calibration import BOARD_SIZE, SQUARE_SIZE

RADIUS = {  # fraction of half a square
    chess.PAWN: 0.55,
    chess.KNIGHT: 0.68,
    chess.BISHOP: 0.68,
    chess.ROOK: 0.72,
    chess.QUEEN: 0.8,
    chess.KING: 0.84,
}


@dataclass(frozen=True)
class Style:
    """One "session": board colours, piece colours and lighting."""

    light: tuple[int, int, int]
    dark: tuple[int, int, int]
    white_piece: tuple[int, int, int]
    black_piece: tuple[int, int, int]
    gain: float
    gradient: float

    @classmethod
    def random(cls, rng: random.Random) -> Style:
        def jitter(base: tuple[int, int, int], spread: int) -> tuple[int, int, int]:
            return tuple(int(min(255, max(0, c + rng.randint(-spread, spread)))) for c in base)  # type: ignore[return-value]

        return cls(
            light=jitter((181, 217, 240), 25),
            dark=jitter((99, 136, 181), 25),
            white_piece=jitter((235, 235, 230), 15),
            black_piece=jitter((45, 40, 40), 15),
            gain=rng.uniform(0.8, 1.2),
            gradient=rng.uniform(-0.15, 0.15),
        )


def _draw_piece(
    img: np.ndarray, center: tuple[int, int], piece: chess.Piece, style: Style, rng: random.Random
) -> None:
    half = SQUARE_SIZE / 2
    r = int(RADIUS[piece.piece_type] * half * 0.85)
    white = piece.color == chess.WHITE
    fill = style.white_piece if white else style.black_piece
    ink = style.black_piece if white else style.white_piece
    ink = tuple(int(0.5 * a + 0.5 * b) for a, b in zip(ink, fill, strict=True))
    cx, cy = center
    # Soft shadow offset down and right, as from an overhead lamp.
    cv2.circle(img, (cx + 4, cy + 5), r, (40, 40, 40), -1, cv2.LINE_AA)
    kind = piece.piece_type
    if kind == chess.ROOK:  # squarish body
        cv2.rectangle(img, (cx - r, cy - r), (cx + r, cy + r), fill, -1)
    else:
        cv2.circle(img, (cx, cy), r, fill, -1, cv2.LINE_AA)
    angle = rng.uniform(0, 2 * math.pi)
    if kind == chess.KNIGHT:  # head: off-centre blob toward a random direction
        hx, hy = cx + int(math.cos(angle) * r * 0.55), cy + int(math.sin(angle) * r * 0.55)
        cv2.circle(img, (hx, hy), max(3, r // 3), ink, -1, cv2.LINE_AA)
    elif kind == chess.BISHOP:  # mitre slit
        dx, dy = int(math.cos(angle) * r * 0.7), int(math.sin(angle) * r * 0.7)
        cv2.line(img, (cx - dx, cy - dy), (cx + dx, cy + dy), ink, 3, cv2.LINE_AA)
        cv2.circle(img, (cx, cy), max(2, r // 5), ink, -1, cv2.LINE_AA)
    elif kind == chess.ROOK:  # crenellation corners
        for sx in (-1, 1):
            for sy in (-1, 1):
                cv2.rectangle(
                    img,
                    (cx + sx * r, cy + sy * r),
                    (cx + sx * (r - r // 3), cy + sy * (r - r // 3)),
                    ink,
                    -1,
                )
    elif kind == chess.QUEEN:  # ring of points
        for k in range(8):
            a = angle + k * math.pi / 4
            px, py = cx + int(math.cos(a) * r * 0.6), cy + int(math.sin(a) * r * 0.6)
            cv2.circle(img, (px, py), 2, ink, -1, cv2.LINE_AA)
    elif kind == chess.KING:  # cross
        t = max(2, r // 6)
        cv2.line(img, (cx - r // 2, cy), (cx + r // 2, cy), ink, t, cv2.LINE_AA)
        cv2.line(img, (cx, cy - r // 2), (cx, cy + r // 2), ink, t, cv2.LINE_AA)
    cv2.circle(img, (cx, cy), r, ink, 1, cv2.LINE_AA)  # rim


def render_warped(board: chess.Board, style: Style, rng: random.Random, noise: float = 4.0):
    """800x800 BGR top-down board, White at the bottom, as the calibrated warp would give."""
    img = np.zeros((BOARD_SIZE, BOARD_SIZE, 3), dtype=np.uint8)
    for sq in chess.SQUARES:
        file, row = chess.square_file(sq), 7 - chess.square_rank(sq)
        light = (file + chess.square_rank(sq)) % 2 == 1
        x0, y0 = file * SQUARE_SIZE, row * SQUARE_SIZE
        img[y0 : y0 + SQUARE_SIZE, x0 : x0 + SQUARE_SIZE] = style.light if light else style.dark
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece is None:
            continue
        file, row = chess.square_file(sq), 7 - chess.square_rank(sq)
        cx = file * SQUARE_SIZE + SQUARE_SIZE // 2 + rng.randint(-8, 8)  # sloppy placement
        cy = row * SQUARE_SIZE + SQUARE_SIZE // 2 + rng.randint(-8, 8)
        _draw_piece(img, (cx, cy), piece, style, rng)

    out = img.astype(np.float32) * style.gain
    out *= 1 + style.gradient * np.linspace(-1, 1, BOARD_SIZE, dtype=np.float32)[None, :, None]
    # Small residual calibration error: a slight perspective wobble of the whole board.
    s = BOARD_SIZE
    src = np.array([[0, 0], [s, 0], [s, s], [0, s]], dtype=np.float32)
    jit = np.array([[rng.uniform(-6, 6), rng.uniform(-6, 6)] for _ in range(4)], np.float32)
    out = cv2.warpPerspective(
        out, cv2.getPerspectiveTransform(src, src + jit), (s, s), borderMode=cv2.BORDER_REPLICATE
    )
    out += np.random.default_rng(rng.randint(0, 2**31)).normal(0, noise, out.shape)
    return np.clip(out, 0, 255).astype(np.uint8)
