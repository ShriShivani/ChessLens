import chess
import numpy as np
import pytest

from edge.detector import DetectorConfig, detect_move, expected_squares, square_changes
from tests.synth import render_board

CASTLE_FEN = "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"
EP_FEN = "8/8/8/3pP3/8/8/8/4K2k w - d6 0 1"


def test_expected_squares_counts():
    assert len(expected_squares(chess.Board(), chess.Move.from_uci("e2e4"))) == 2
    castle = chess.Board(CASTLE_FEN)
    assert len(expected_squares(castle, chess.Move.from_uci("e1g1"))) == 4
    assert len(expected_squares(castle, chess.Move.from_uci("e1c1"))) == 4
    assert len(expected_squares(chess.Board(EP_FEN), chess.Move.from_uci("e5d6"))) == 3


@pytest.mark.parametrize(
    "fen,uci",
    [
        (chess.STARTING_FEN, "g1f3"),
        (CASTLE_FEN, "e1g1"),
        (CASTLE_FEN, "e1c1"),
        (CASTLE_FEN, "e1f1"),
        (EP_FEN, "e5d6"),
        ("4k3/P7/8/8/8/8/8/4K3 w - - 0 1", "a7a8q"),
        ("rnbqkbnr/pppp1ppp/8/4p3/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 0 2", "d4e5"),
    ],
)
def test_detects_clean_moves(fen, uci):
    board = chess.Board(fen)
    move = chess.Move.from_uci(uci)
    before = render_board(board)
    board.push(move)
    result = detect_move(chess.Board(fen), before, render_board(board))
    assert result.status == "move"
    assert result.move == move


def test_no_change_and_exposure_shift_are_ignored():
    img = render_board(chess.Board())
    assert detect_move(chess.Board(), img, img).status == "nochange"
    dimmer = np.clip(img.astype(float) * 0.85 + 5, 0, 255).astype(np.uint8)
    assert detect_move(chess.Board(), img, dimmer).status == "nochange"


def test_many_changed_squares_is_treated_as_occlusion():
    a = render_board(chess.Board())
    b = a.copy()
    b[200:600, 100:700] = 20  # a big dark blob, like a hand
    assert detect_move(chess.Board(), a, b).status == "occluded"


def test_change_no_legal_move_explains_is_not_blindly_accepted():
    board = chess.Board()
    odd = chess.Board()
    odd.remove_piece_at(chess.E2)  # a piece vanishes with no legal move behind it
    result = detect_move(board, render_board(board), render_board(odd))
    assert result.status == "uncertain"
    assert result.move is None
    assert result.candidates


def test_changes_are_normalised():
    img = render_board(chess.Board())
    assert square_changes(img, img, DetectorConfig()).max() < 0.05
