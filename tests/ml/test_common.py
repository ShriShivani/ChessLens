import chess
import numpy as np
import pytest

from ml.common import (
    CLASS_NAMES,
    NUM_CLASSES,
    board_labels,
    class_of,
    join_probs,
    piece_of,
    split_label,
    square_crops,
)
from ml.data import class_counts, class_weights, discover, load_games, read_meta, save_game
from ml.splits import assert_no_leakage, split_groups
from tests.ml.helpers import probs_for
from tests.synth import render_board


def test_class_names_and_roundtrip():
    assert len(CLASS_NAMES) == NUM_CLASSES == 13
    assert CLASS_NAMES[0] == "empty" and CLASS_NAMES[1] == "wP" and CLASS_NAMES[12] == "bK"
    for cls in range(NUM_CLASSES):
        assert class_of(piece_of(cls)) == cls


def test_board_labels_match_the_start_position():
    labels = board_labels(chess.Board())
    assert labels[chess.E1] == class_of(chess.Piece(chess.KING, chess.WHITE))
    assert labels[chess.D8] == class_of(chess.Piece(chess.QUEEN, chess.BLACK))
    assert labels[chess.E4] == 0
    assert (labels == 0).sum() == 32


def test_split_label_separates_colour_and_type():
    occ, typ = split_label(np.arange(NUM_CLASSES))
    assert occ.tolist() == [0] + [1] * 6 + [2] * 6
    assert typ.tolist() == [-1] + list(range(6)) * 2


def test_join_probs_is_a_distribution():
    rng = np.random.default_rng(0)
    occ = rng.dirichlet(np.ones(3), 5)
    typ = rng.dirichlet(np.ones(6), 5)
    joined = join_probs(occ, typ)
    assert joined.shape == (5, 13)
    np.testing.assert_allclose(joined.sum(1), 1.0, rtol=1e-5)


def test_square_crops_shape_order_and_padding():
    board = chess.Board(None)
    board.set_piece_at(chess.A1, chess.Piece(chess.KING, chess.WHITE))
    warped = render_board(board)
    crops = square_crops(warped, 96)
    assert crops.shape == (64, 96, 96, 3) and crops.dtype == np.uint8
    # Against the same board without the piece, only the a1 crop may change much.
    empty = square_crops(render_board(chess.Board(None)), 96).astype(float)
    diffs = [np.abs(crops[sq].astype(float) - empty[sq]).mean() for sq in chess.SQUARES]
    assert int(np.argmax(diffs)) == chess.A1
    assert square_crops(warped, 112).shape == (64, 112, 112, 3)


def test_square_crops_rejects_wrong_board_size():
    with pytest.raises(ValueError):
        square_crops(np.zeros((400, 400, 3), np.uint8))


def test_splits_never_mix_a_game_or_session():
    games = [f"g{i}" for i in range(12)]
    sessions = {g: f"s{i % 4}" for i, g in enumerate(games)}
    a = split_groups(games, sessions, seed=1)
    assert a == split_groups(games, sessions, seed=1)  # deterministic
    assert_no_leakage(a, sessions)
    assert set(a.values()) == {"train", "val", "test"}
    by_session = {}
    for g, split in a.items():
        by_session.setdefault(sessions[g], set()).add(split)
    assert all(len(v) == 1 for v in by_session.values())


def test_split_without_sessions_groups_by_game_and_handles_tiny_sets():
    assert set(split_groups(["a", "b"]).values()) == {"train"}
    many = split_groups([f"g{i}" for i in range(20)])
    assert list(many.values()).count("test") >= 1
    with pytest.raises(ValueError):
        split_groups(["a"], fractions=(0.5, 0.5, 0.5))


def test_leakage_check_catches_a_bad_split():
    with pytest.raises(AssertionError):
        assert_no_leakage({"g1": "train", "g2": "test"}, {"g1": "lamp", "g2": "lamp"})


def test_save_load_roundtrip_and_validation(tmp_path):
    crops = np.random.default_rng(0).integers(0, 255, (128, 8, 8, 3), dtype=np.uint8)
    labels = np.tile(board_labels(chess.Board()), 2)
    save_game(tmp_path / "a.npz", crops, labels, game="a", session="s")
    save_game(tmp_path / "b.npz", crops, labels, game="b", session="s")
    assert read_meta(tmp_path / "a.npz") == ("a", "s")
    data = load_games(discover(tmp_path))
    assert len(data) == 256 and data.boards == 4 and data.games == ["a", "b"]
    assert data.game.tolist().count(1) == 128
    with pytest.raises(ValueError):
        save_game(tmp_path / "bad.npz", crops[:10], labels[:10], "x", "s")
    with pytest.raises(ValueError):
        load_games([])


def test_class_weights_are_finite_and_favour_rare_classes():
    labels = board_labels(chess.Board())
    w_occ, w_typ = class_weights(labels)
    assert np.isfinite(w_occ).all() and np.isfinite(w_typ).all()
    assert w_occ[1] > w_occ[0]  # white squares (16) are rarer than empty ones (32)
    counts = class_counts(labels)
    assert counts.sum() == 64


def test_probs_helper_is_consistent():
    p = probs_for(chess.Board())
    assert p.argmax(1).tolist() == board_labels(chess.Board()).tolist()
