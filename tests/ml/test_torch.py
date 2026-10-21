"""Tests that need torch / onnxruntime; skipped when they are not installed."""

import random
from pathlib import Path

import chess
import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("onnxruntime")
pytest.importorskip("yaml")

from ml.augment import augment  # noqa: E402
from ml.common import board_labels, split_label, square_crops  # noqa: E402
from ml.data import save_game  # noqa: E402
from ml.evaluate import (  # noqa: E402
    evaluate_arrays,
    evaluate_run,
    expected_calibration_error,
    fit_temperature,
)
from ml.export_onnx import export  # noqa: E402
from ml.infer import SquareClassifier  # noqa: E402
from ml.model import SquareNet  # noqa: E402
from ml.synthetic import Style, render_warped  # noqa: E402
from ml.train import Config, train  # noqa: E402
from tests.synth import random_game  # noqa: E402


def make_games(folder: Path, games: int = 4, positions: int = 3) -> None:
    """Tiny synthetic dataset: `games` games over four sessions, 64-square boards."""
    folder.mkdir(parents=True, exist_ok=True)
    styles = [Style.random(random.Random(s)) for s in range(4)]
    for g in range(games):
        rng = random.Random(g)
        moves = random_game(g, 40)
        board, crops, labels = chess.Board(), [], []
        for i, m in enumerate(moves):
            board.push(m)
            if i % (len(moves) // positions) == 0 and len(crops) < positions:
                crops.append(square_crops(render_warped(board, styles[g % 4], rng), 96))
                labels.append(board_labels(board))
        save_game(
            folder / f"g{g}.npz",
            np.concatenate(crops),
            np.concatenate(labels),
            game=f"g{g}",
            session=f"s{g % 4}",
        )


def test_model_shapes_and_normalisation():
    model = SquareNet("tiny").eval()
    occ, typ = model(torch.rand(5, 3, 96, 96))
    assert occ.shape == (5, 3) and typ.shape == (5, 6)
    # Input normalisation lives inside the model, so 0..1 RGB goes in directly.
    assert model.mean.shape == (1, 3, 1, 1)


def test_augmentation_keeps_shape_and_type_and_changes_pixels():
    img = np.random.default_rng(0).integers(0, 255, (96, 96, 3), dtype=np.uint8)
    out = augment(img, np.random.default_rng(1))
    assert out.shape == img.shape and out.dtype == np.uint8 and not np.array_equal(out, img)


def test_evaluate_arrays_on_perfect_and_wrong_predictions():
    labels = np.tile(board_labels(chess.Board()), 2)
    occ_y, typ_y = split_label(labels)
    occ = np.eye(3)[occ_y] * 10
    typ = np.eye(6)[np.where(typ_y < 0, 0, typ_y)] * 10
    perfect = evaluate_arrays(occ, typ, labels)
    assert perfect["class_accuracy"] == 1.0 and perfect["full_board_exact_match"] == 1.0
    assert perfect["boards"] == 2
    flipped = evaluate_arrays(np.roll(occ, 1, axis=1), typ, labels)
    assert flipped["occupancy_accuracy"] == 0.0 and flipped["full_board_exact_match"] == 0.0
    assert sum(sum(r) for r in perfect["confusion_matrix"]) == len(labels)


def test_temperature_and_ece():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 3, 2000)
    logits = np.eye(3)[y] * 3 + rng.normal(0, 2.5, (2000, 3))  # overconfident-ish scores
    t = fit_temperature(logits, y)
    assert t > 0
    probs = np.exp(logits / t) / np.exp(logits / t).sum(1, keepdims=True)
    raw = np.exp(logits) / np.exp(logits).sum(1, keepdims=True)
    assert expected_calibration_error(probs, y) <= expected_calibration_error(raw, y) + 1e-6
    assert fit_temperature(logits, -np.ones(2000, dtype=int)) == 1.0


def test_train_evaluate_export_and_classify_end_to_end(tmp_path):
    data = tmp_path / "data"
    make_games(data, games=8, positions=3)
    cfg = Config(
        name="tiny_test",
        data_dirs=[str(data)],
        epochs=3,
        batch_size=64,
        patience=3,
        out_dir=str(tmp_path / "runs"),
        augment=False,
        seed=0,
    )
    run = train(cfg)
    for name in ("model.pt", "config.json", "split.json", "metrics.json"):
        assert (run / name).exists()

    result = evaluate_run(run, "test", None)
    assert result["boards"] > 0 and 0.0 <= result["class_accuracy"] <= 1.0
    assert (run / "errors_test.png").exists() or result["class_accuracy"] == 1.0

    # ONNX export agrees with torch, and inference returns valid probabilities.
    model = SquareNet("tiny")
    model.load_state_dict(torch.load(run / "model.pt", map_location="cpu"))
    onnx_path = tmp_path / "m.onnx"
    diff = export(model, onnx_path, 96, (1.0, 1.0))
    assert diff < 1e-3
    clf = SquareClassifier(onnx_path)
    rng = random.Random(5)
    board = chess.Board()
    warped = render_warped(board, Style.random(rng), rng)
    probs = clf.predict(warped)
    assert probs.shape == (64, 13)
    np.testing.assert_allclose(probs.sum(1), 1.0, rtol=1e-4)
    assert clf.latency_ms(warped, runs=3) > 0


def test_trained_model_beats_the_majority_class_on_occupancy(tmp_path):
    """Fixture check from the ML plan: a briefly trained model must be clearly useful."""
    data = tmp_path / "data"
    make_games(data, games=8, positions=3)
    cfg = Config(
        name="quick",
        data_dirs=[str(data)],
        epochs=4,
        batch_size=64,
        patience=4,
        out_dir=str(tmp_path / "runs"),
        augment=False,
        seed=1,
    )
    run = train(cfg)
    model = SquareNet("tiny")
    model.load_state_dict(torch.load(run / "model.pt", map_location="cpu"))
    onnx_path = tmp_path / "q.onnx"
    export(model, onnx_path, 96, (1.0, 1.0))
    clf = SquareClassifier(onnx_path)
    rng = random.Random(9)
    board = chess.Board("r3k2r/pp3ppp/2n1bn2/3pp3/3P4/2N1BN2/PPP1QPPP/R3K2R w KQkq - 0 1")
    probs = clf.predict(render_warped(board, Style.random(random.Random(0)), rng))
    occ = np.stack([probs[:, 0], probs[:, 1:7].sum(1), probs[:, 7:].sum(1)], 1).argmax(1)
    truth = split_label(board_labels(board))[0]
    majority = max(np.bincount(truth)) / 64
    assert (occ == truth).mean() > majority + 0.1
