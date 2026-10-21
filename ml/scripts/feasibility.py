"""Day-1 feasibility test on a small sample of labelled crops (ML plan, section 3).

Run:  python -m ml.scripts.feasibility ml/data/real --crops 500

Does two things:
  1. fits a tiny logistic-regression model on empty/white/black and reports held-out accuracy
     (games are kept apart, so this is not inflated by near-identical frames);
  2. writes a contact sheet of KING / QUEEN and BISHOP / KNIGHT crops. LOOK AT IT. If you cannot
     tell the pieces apart by eye, a model will not either: tilt the camera or rely on the tracker.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

from ml.common import CLASS_NAMES, split_label
from ml.data import CropSet, discover, load_games


def features(crops: np.ndarray, side: int = 16) -> np.ndarray:
    small = np.stack([cv2.resize(c, (side, side), interpolation=cv2.INTER_AREA) for c in crops])
    x = small.reshape(len(crops), -1).astype(np.float32) / 255.0
    return (x - x.mean(1, keepdims=True)) / (x.std(1, keepdims=True) + 1e-6)


def fit_softmax(x: np.ndarray, y: np.ndarray, classes: int, steps: int = 300, lr: float = 0.5):
    w = np.zeros((x.shape[1], classes), dtype=np.float32)
    b = np.zeros(classes, dtype=np.float32)
    onehot = np.eye(classes, dtype=np.float32)[y]
    for _ in range(steps):
        z = x @ w + b
        z -= z.max(1, keepdims=True)
        p = np.exp(z) / np.exp(z).sum(1, keepdims=True)
        g = (p - onehot) / len(x)
        w -= lr * (x.T @ g + 1e-3 * w)
        b -= lr * g.sum(0)
    return w, b


def accuracy(x: np.ndarray, y: np.ndarray, w: np.ndarray, b: np.ndarray) -> float:
    return float(((x @ w + b).argmax(1) == y).mean()) if len(y) else float("nan")


def sample(data: CropSet, count: int, seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).choice(len(data), min(count, len(data)), replace=False)


def pair_sheet(data: CropSet, path: Path, per_class: int = 14) -> None:
    """Rows of crops for the pairs that are hard from above."""
    rng = np.random.default_rng(1)
    rows = []
    for name in ("wK", "wQ", "wB", "wN", "bK", "bQ", "bB", "bN"):
        idx = np.flatnonzero(data.labels == CLASS_NAMES.index(name))
        pick = rng.choice(idx, min(per_class, len(idx)), replace=False) if len(idx) else []
        tiles = [data.crops[i] for i in pick]
        tiles += [np.full_like(data.crops[0], 255)] * (per_class - len(tiles))
        rows.append(np.concatenate(tiles, axis=1))
    cv2.imwrite(str(path), cv2.cvtColor(np.concatenate(rows, axis=0), cv2.COLOR_RGB2BGR))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("data", type=Path, help="folder of .npz crop files")
    ap.add_argument("--crops", type=int, default=500)
    ap.add_argument("--out", type=Path, default=Path("ml/data/feasibility_pairs.png"))
    args = ap.parse_args(argv)

    files = discover(args.data)
    if len(files) < 2:
        print("Need at least 2 games so train and test crops come from different games.")
        return 2
    half = max(1, len(files) // 2)
    train, test = load_games(files[:half]), load_games(files[half:])
    tr, te = sample(train, args.crops), sample(test, args.crops)
    ytr, yte = split_label(train.labels[tr])[0], split_label(test.labels[te])[0]
    xtr, xte = features(train.crops[tr]), features(test.crops[te])
    w, b = fit_softmax(xtr, ytr, 3)
    majority = float(np.bincount(yte, minlength=3).max() / len(yte))
    print(f"empty/white/black accuracy on held-out games: {accuracy(xte, yte, w, b):.1%}")
    print(f"(always guessing the most common class would score {majority:.1%})")

    typ_tr, typ_te = split_label(train.labels)[1], split_label(test.labels)[1]
    occ_tr, occ_te = typ_tr >= 0, typ_te >= 0
    if occ_tr.sum() >= 30 and occ_te.sum() >= 30:
        xt, xe = features(train.crops[occ_tr][:1000]), features(test.crops[occ_te][:1000])
        wt, bt = fit_softmax(xt, typ_tr[occ_tr][:1000], 6)
        acc = accuracy(xe, typ_te[occ_te][:1000], wt, bt)
        print(f"piece type accuracy (6 classes, linear model): {acc:.1%}")
    pair_sheet(test, args.out)
    print(f"wrote {args.out}: rows are wK wQ wB wN bK bQ bB bN. Can YOU tell them apart? If not,")
    print("tilt the camera 15-30 degrees or lean on the move tracker for piece identity.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
