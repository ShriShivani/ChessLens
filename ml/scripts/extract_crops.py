"""Auto-label crops from a real clip: video + ground-truth PGN + calibration -> labelled crops.

Run:
  python -m ml.scripts.extract_crops tests/real/clip1.mp4 --out ml/data/real --session home-lamp

The tracker runs over the video; at every stable frame the 64 crops are labelled with the
tracker's board. Labels are only trusted while the tracker's moves equal the PGN's moves so
far, so a tracker mistake never becomes a wrong label. Spot-check a sample sheet (written next
to the output) by eye: the plan calls for checking about 5% of crops.
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import chess
import cv2
import numpy as np

from edge.calibration import Calibration
from edge.cli import frames, open_source
from edge.pipeline import Pipeline
from ml.common import CLASS_NAMES, DEFAULT_INPUT, board_labels, square_crops
from ml.data import save_game
from tests.synth import load_pgn_moves


def collect(
    video: str | Path, truth: list[chess.Move], calibration: Calibration, size: int
) -> tuple[np.ndarray, np.ndarray, int]:
    """Return (crops, labels, frames_skipped) for every stable frame with a trusted tracker."""
    cap, live = open_source(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {video}")
    pipe = Pipeline(calibration)
    crops, labels, skipped = [], [], 0
    seen = None
    for frame, t in frames(cap, live):
        pipe.process_frame(frame, t)
        if pipe.last_stable is None or pipe.last_stable is seen:
            continue  # the gate has not released a new stable frame
        seen = pipe.last_stable
        stack = pipe.board.move_stack
        if stack != truth[: len(stack)]:
            skipped += 1  # tracker disagrees with the PGN: do not label from it
            continue
        crops.append(square_crops(pipe.last_stable, size))
        labels.append(board_labels(pipe.board))
    cap.release()
    if not crops:
        raise RuntimeError("no trusted stable frames; check the calibration and the PGN")
    return np.concatenate(crops), np.concatenate(labels), skipped


def sample_sheet(crops: np.ndarray, labels: np.ndarray, path: Path, fraction: float = 0.05) -> None:
    """Contact sheet of a random sample (default 5%) with labels, for manual spot-checking."""
    rng = random.Random(0)
    n = max(24, int(len(labels) * fraction))
    idx = rng.sample(range(len(labels)), min(n, len(labels)))
    cols = 12
    tile = crops.shape[1]
    rows = -(-len(idx) // cols)
    sheet = np.full((rows * (tile + 14), cols * tile, 3), 255, dtype=np.uint8)
    for k, i in enumerate(idx):
        r, c = divmod(k, cols)
        y, x = r * (tile + 14), c * tile
        sheet[y + 14 : y + 14 + tile, x : x + tile] = crops[i]
        cv2.putText(sheet, CLASS_NAMES[labels[i]], (x + 2, y + 11), 0, 0.4, (0, 0, 0), 1)
    cv2.imwrite(str(path), cv2.cvtColor(sheet, cv2.COLOR_RGB2BGR))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video", type=Path)
    ap.add_argument("--pgn", type=Path, help="default: next to the video, same name")
    ap.add_argument("--calibration", type=Path, help="default: NAME.calibration.json")
    ap.add_argument("--out", type=Path, default=Path("ml/data/real"))
    ap.add_argument("--session", required=True, help="lighting/board setup name (used to split)")
    ap.add_argument("--size", type=int, default=DEFAULT_INPUT)
    args = ap.parse_args(argv)

    pgn = args.pgn or args.video.with_suffix(".pgn")
    cal = args.calibration or args.video.with_suffix(".calibration.json")
    crops, labels, skipped = collect(
        args.video, load_pgn_moves(pgn), Calibration.load(cal), args.size
    )
    args.out.mkdir(parents=True, exist_ok=True)
    name = args.video.stem
    save_game(
        args.out / f"{name}.npz",
        crops,
        labels,
        game=name,
        session=args.session,
        source=str(args.video),
    )
    sample_sheet(crops, labels, args.out / f"{name}.spotcheck.png")
    print(f"{name}: {len(labels) // 64} boards, {skipped} frames skipped (tracker != PGN)")
    print(f"spot-check sheet: {args.out / f'{name}.spotcheck.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
