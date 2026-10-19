"""Synthetic chess footage: render positions, push them through a fake camera."""

from __future__ import annotations

import random
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import chess
import chess.pgn
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from edge.calibration import BOARD_SIZE, SQUARE_SIZE, Calibration

FRAME_W, FRAME_H = 960, 540
LIGHT = (181, 217, 240)  # BGR
DARK = (99, 136, 181)
BASE_QUAD = np.array([[250, 45], [712, 60], [750, 502], [218, 487]], dtype=np.float32)
ROTATIONS = {
    "bottom": None,
    "top": cv2.ROTATE_180,
    "left": cv2.ROTATE_90_CLOCKWISE,
    "right": cv2.ROTATE_90_COUNTERCLOCKWISE,
}
_FONT = ImageFont.load_default(size=44)


@dataclass(frozen=True)
class SynthConfig:
    fps: float = 10.0
    hold_frames: int = 12  # still frames between moves
    occlusion: bool = True  # a hand moves over the board during each move
    noise_sigma: float = 3.0
    lighting_jitter: float = 0.04  # per-move random walk of gain
    corner_jitter: float = 2.0  # px error when "clicking" corners
    white_side: str = "bottom"
    seed: int = 0


def render_board(board: chess.Board) -> np.ndarray:
    """Top-down 800x800 BGR image, White at the bottom."""
    img = Image.new("RGB", (BOARD_SIZE, BOARD_SIZE))
    draw = ImageDraw.Draw(img)
    for sq in chess.SQUARES:
        file, row = chess.square_file(sq), 7 - chess.square_rank(sq)
        x0, y0 = file * SQUARE_SIZE, row * SQUARE_SIZE
        light = (file + chess.square_rank(sq)) % 2 == 1
        bgr = LIGHT if light else DARK
        draw.rectangle([x0, y0, x0 + SQUARE_SIZE, y0 + SQUARE_SIZE], fill=bgr[::-1])
        piece = board.piece_at(sq)
        if piece is None:
            continue
        r = 30 if piece.piece_type == chess.PAWN else 38
        cx, cy = x0 + SQUARE_SIZE // 2, y0 + SQUARE_SIZE // 2
        white = piece.color == chess.WHITE
        fill, ink = ((250, 250, 245), (20, 20, 20)) if white else ((35, 30, 30), (240, 240, 235))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill, outline=ink, width=3)
        draw.text((cx, cy), piece.symbol().upper(), font=_FONT, fill=ink, anchor="mm")
    return cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)


def _square_center(sq: chess.Square) -> tuple[int, int]:
    file, row = chess.square_file(sq), 7 - chess.square_rank(sq)
    return file * SQUARE_SIZE + SQUARE_SIZE // 2, row * SQUARE_SIZE + SQUARE_SIZE // 2


def draw_hand(img: np.ndarray, center: tuple[int, int], rng: random.Random) -> None:
    """Skin-coloured blob with a wrist trailing off the bottom of the board."""
    skin = (rng.randint(120, 160), rng.randint(150, 185), rng.randint(200, 235))
    x, y = center
    cv2.ellipse(img, (x, y), (70, 45), rng.randint(-30, 30), 0, 360, skin, -1)
    cv2.rectangle(img, (x - 40, y), (x + 40, BOARD_SIZE + 100), skin, -1)


class Camera:
    """Projects the top-down board into a perspective camera frame with lighting and noise."""

    def __init__(self, cfg: SynthConfig, rng: random.Random) -> None:
        self.cfg, self.rng = cfg, rng
        self.np_rng = np.random.default_rng(cfg.seed)
        jitter = np.array(
            [[rng.uniform(-8, 8), rng.uniform(-8, 8)] for _ in range(4)], dtype=np.float32
        )
        self.quad = BASE_QUAD + jitter
        src = np.array(
            [[0, 0], [BOARD_SIZE, 0], [BOARD_SIZE, BOARD_SIZE], [0, BOARD_SIZE]], dtype=np.float32
        )
        self.h = cv2.getPerspectiveTransform(src, self.quad)
        ys, xs = np.mgrid[0:FRAME_H, 0:FRAME_W]
        wood = 90 + 25 * np.sin(xs / 37.0) + 10 * np.sin(ys / 11.0)
        self.background = np.dstack([wood * 0.6, wood * 0.8, wood]).astype(np.float32)
        self.mask = cv2.warpPerspective(
            np.ones((BOARD_SIZE, BOARD_SIZE), np.float32), self.h, (FRAME_W, FRAME_H)
        )[..., None]
        self.gain = rng.uniform(0.85, 1.15)
        self.offset = rng.uniform(-8, 8)
        self.slope = rng.uniform(-0.08, 0.08)
        self._noise = [
            self.np_rng.standard_normal((FRAME_H, FRAME_W, 3), dtype=np.float32) * cfg.noise_sigma
            for _ in range(6)
        ]
        self._xs = np.linspace(-1, 1, FRAME_W, dtype=np.float32)[None, :, None]

    def drift(self) -> None:
        self.gain *= 1 + self.rng.uniform(-1, 1) * self.cfg.lighting_jitter

    def shoot(self, board_img: np.ndarray) -> np.ndarray:
        rot = ROTATIONS[self.cfg.white_side]
        src = board_img if rot is None else cv2.rotate(board_img, rot)
        frame = cv2.warpPerspective(src, self.h, (FRAME_W, FRAME_H)).astype(np.float32)
        frame -= self.background
        frame *= self.mask
        frame += self.background
        flicker = 1 + self.rng.uniform(-0.004, 0.004)
        frame *= self.gain * flicker * (1 + self.slope * self._xs)
        frame += self.offset
        noise = self._noise[self.rng.randrange(len(self._noise))]
        frame += np.roll(noise, (self.rng.randrange(FRAME_H), self.rng.randrange(FRAME_W)), (0, 1))
        return np.clip(frame, 0, 255).astype(np.uint8)

    def calibration(self) -> Calibration:
        j = self.cfg.corner_jitter
        clicked = tuple(
            (float(x + self.rng.uniform(-j, j)), float(y + self.rng.uniform(-j, j)))
            for x, y in self.quad
        )
        return Calibration(clicked, self.cfg.white_side)


@dataclass
class SynthGame:
    calibration: Calibration
    frames: Iterator[tuple[np.ndarray, float, bool]]  # frame, time, is_move_phase
    moves: list[chess.Move]


def _transition(
    before: chess.Board, move: chess.Move, cam: Camera, cfg: SynthConfig, rng: random.Random
) -> Iterator[np.ndarray]:
    """Frames covering one move: hand in, piece swaps under the hand, hand out."""
    after = before.copy()
    after.push(move)
    old_img, new_img = render_board(before), render_board(after)
    if not cfg.occlusion:
        yield cam.shoot(new_img)
        return
    src, dst = _square_center(move.from_square), _square_center(move.to_square)
    off = (BOARD_SIZE + 150, BOARD_SIZE // 2)
    steps = ((off, old_img), (src, old_img), (dst, new_img), (dst, new_img), (off, new_img))
    for pos, img in steps:
        frame = img.copy()
        draw_hand(frame, pos, rng)
        yield cam.shoot(frame)


def play(
    moves: list[chess.Move], cfg: SynthConfig | None = None, start: chess.Board | None = None
) -> SynthGame:
    cfg = cfg or SynthConfig()
    rng = random.Random(cfg.seed)
    cam = Camera(cfg, rng)

    def gen() -> Iterator[tuple[np.ndarray, float, bool]]:
        board = start.copy() if start else chess.Board()
        n = 0

        def stamp(frame: np.ndarray, moving: bool = False) -> tuple[np.ndarray, float, bool]:
            nonlocal n
            n += 1
            return frame, (n - 1) / cfg.fps, moving

        img = render_board(board)
        for _ in range(cfg.hold_frames):
            yield stamp(cam.shoot(img))
        for move in moves:
            for frame in _transition(board, move, cam, cfg, rng):
                yield stamp(frame, moving=True)
            board.push(move)
            cam.drift()
            img = render_board(board)
            for _ in range(cfg.hold_frames):
                yield stamp(cam.shoot(img))

    return SynthGame(cam.calibration(), gen(), list(moves))


def random_game(seed: int, max_plies: int = 60) -> list[chess.Move]:
    """Random legal game (promotions always to queen)."""
    rng = random.Random(seed)
    board = chess.Board()
    moves: list[chess.Move] = []
    while len(moves) < max_plies and not board.is_game_over():
        legal = [m for m in board.legal_moves if m.promotion in (None, chess.QUEEN)]
        move = rng.choice(legal)
        board.push(move)
        moves.append(move)
    return moves


def load_pgn_moves(path: str | Path) -> list[chess.Move]:
    with open(path, encoding="utf-8") as fh:
        game = chess.pgn.read_game(fh)
    if game is None:
        raise ValueError(f"no game in {path}")
    return list(game.mainline_moves())


def categorize(board: chess.Board, move: chess.Move) -> str:
    if board.is_castling(move):
        return "castling"
    if board.is_en_passant(move):
        return "en_passant"
    if move.promotion:
        return "promotion"
    return "capture" if board.is_capture(move) else "quiet"
