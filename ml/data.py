"""On-disk crop sets (one compressed .npz per game) and class weights."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ml.common import NUM_CLASSES, split_label


@dataclass
class CropSet:
    """Crops from one or more games. Rows are grouped in boards of 64 (square order a1..h8)."""

    crops: np.ndarray  # (N, S, S, 3) uint8 RGB
    labels: np.ndarray  # (N,) int64 class index 0..12
    game: np.ndarray  # (N,) int index into `games`
    games: list[str]

    def __len__(self) -> int:
        return len(self.labels)

    @property
    def boards(self) -> int:
        return len(self.labels) // 64


def save_game(
    path: str | Path,
    crops: np.ndarray,
    labels: np.ndarray,
    game: str,
    session: str,
    source: str = "",
) -> None:
    """Write one game. `crops` is (F*64, S, S, 3); `labels` is (F*64,)."""
    if len(crops) != len(labels) or len(labels) % 64:
        raise ValueError("crops and labels must be whole boards of 64 squares")
    np.savez_compressed(
        path,
        crops=crops.astype(np.uint8),
        labels=labels.astype(np.int8),
        game=np.array(game),
        session=np.array(session),
        source=np.array(source),
    )


def read_meta(path: str | Path) -> tuple[str, str]:
    with np.load(path) as z:
        return str(z["game"]), str(z["session"])


def load_games(paths: Sequence[str | Path]) -> CropSet:
    crops, labels, game_idx, names = [], [], [], []
    for i, p in enumerate(paths):
        with np.load(p) as z:
            crops.append(z["crops"])
            labels.append(z["labels"].astype(np.int64))
            names.append(str(z["game"]))
            game_idx.append(np.full(len(z["labels"]), i, dtype=np.int64))
    if not crops:
        raise ValueError("no crop files given")
    return CropSet(np.concatenate(crops), np.concatenate(labels), np.concatenate(game_idx), names)


def discover(folder: str | Path) -> list[Path]:
    return sorted(Path(folder).glob("*.npz"))


def class_weights(labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Inverse-frequency weights (mean 1) for the occupancy head and the type head.

    Classes absent from the data get weight 1 so they cannot produce infinities.
    """
    occ, typ = split_label(labels)

    def weights(values: np.ndarray, n: int) -> np.ndarray:
        counts = np.bincount(values[values >= 0], minlength=n).astype(np.float64)
        w = np.where(counts > 0, counts.sum() / np.maximum(counts, 1) / n, 1.0)
        return (w / w.mean()).astype(np.float32)

    return weights(occ, 3), weights(typ, 6)


def class_counts(labels: np.ndarray) -> np.ndarray:
    return np.bincount(labels, minlength=NUM_CLASSES)
