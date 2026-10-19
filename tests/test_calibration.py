import random

import chess
import numpy as np
import pytest

from edge.calibration import BOARD_SIZE, Calibration, square_bounds
from edge.detector import DetectorConfig, square_changes
from tests.synth import Camera, SynthConfig, render_board


def test_save_load_roundtrip(tmp_path):
    cal = Calibration(((1, 2), (3, 4), (5, 6), (7, 8)), "top")
    cal.save(tmp_path / "c.json")
    assert Calibration.load(tmp_path / "c.json") == cal


def test_rejects_bad_input():
    with pytest.raises(ValueError):
        Calibration(((0, 0),) * 3)
    with pytest.raises(ValueError):
        Calibration(((0, 0),) * 4, "middle")


def test_flipped_swaps_side():
    cal = Calibration(((0, 0),) * 4, "bottom")
    assert cal.flipped().white_side == "top"
    assert cal.flipped().flipped().white_side == "bottom"


@pytest.mark.parametrize("side", ["bottom", "top", "left", "right"])
def test_warp_puts_squares_in_the_right_place_for_every_orientation(side):
    cfg = SynthConfig(white_side=side, noise_sigma=0.0, corner_jitter=0.0, seed=3)
    cam = Camera(cfg, random.Random(3))
    cal = cam.calibration()
    empty = cal.warp(cam.shoot(render_board(chess.Board(None))))
    assert empty.shape[:2] == (BOARD_SIZE, BOARD_SIZE)
    for square in (chess.A1, chess.H1, chess.A8, chess.D4):
        board = chess.Board(None)
        board.set_piece_at(square, chess.Piece(chess.KING, chess.WHITE))
        with_piece = cal.warp(cam.shoot(render_board(board)))
        changes = square_changes(empty, with_piece, DetectorConfig())
        assert int(np.argmax(changes)) == square


def test_square_bounds_white_at_bottom():
    y0, y1, x0, x1 = square_bounds(chess.A1)
    assert (y0, x0) == (700, 0) and (y1, x1) == (800, 100)
    y0, _, x0, _ = square_bounds(chess.H8)
    assert (y0, x0) == (0, 700)
