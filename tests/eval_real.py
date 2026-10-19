"""Accuracy evaluation on REAL recorded clips (kept separate from the synthetic eval).

Run:  python -m tests.eval_real [--dir tests/real] [--json OUT]

For each clip `NAME.mp4` the folder must also hold `NAME.pgn` (ground truth, full game)
and `NAME.calibration.json` (from `python -m edge calibrate`). See tests/real/README.md.

Scoring is deliberately stricter than the synthetic eval: there is NO operator resync.
The pipeline runs start to finish and its moves are compared with the truth in order.
  correct_prefix  moves correct before the first wrong or missing move
  accepted        moves the pipeline auto-accepted
  uncertain       times it flagged a move instead of guessing
A game counts as fully correct only if every move matched with no intervention.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import chess

from edge.calibration import Calibration
from edge.cli import frames, open_source
from edge.pipeline import Pipeline
from tests.synth import load_pgn_moves

ROOT = Path(__file__).parent


@dataclass
class ClipResult:
    name: str
    truth_moves: int
    accepted: int
    correct_prefix: int
    uncertain: int

    @property
    def fully_correct(self) -> bool:
        return self.correct_prefix == self.truth_moves and self.accepted == self.truth_moves


def run_clip(video: Path, truth: list[chess.Move], calibration: Calibration) -> ClipResult:
    cap, live = open_source(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {video}")
    pipe = Pipeline(calibration)
    uncertain = 0
    for frame, t in frames(cap, live):
        uncertain += sum(1 for e in pipe.process_frame(frame, t) if e.kind == "uncertain")
    cap.release()
    got = pipe.board.move_stack
    prefix = 0
    for a, b in zip(got, truth, strict=False):
        if a != b:
            break
        prefix += 1
    return ClipResult(video.stem, len(truth), len(got), prefix, uncertain)


def find_clips(folder: Path) -> list[Path]:
    clips = []
    for video in sorted(folder.glob("*.mp4")):
        if video.with_suffix(".pgn").exists() and video.with_suffix(".calibration.json").exists():
            clips.append(video)
    return clips


def summarize(results: list[ClipResult]) -> dict:
    total = sum(r.truth_moves for r in results)
    return {
        "clips": len(results),
        "truth_moves": total,
        "correct_prefix_moves": sum(r.correct_prefix for r in results),
        "prefix_accuracy": (sum(r.correct_prefix for r in results) / total) if total else 0.0,
        "fully_correct_clips": sum(1 for r in results if r.fully_correct),
        "uncertain_events": sum(r.uncertain for r in results),
        "per_clip": [asdict(r) for r in results],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--dir", type=Path, default=ROOT / "real")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args(argv)

    clips = find_clips(args.dir)
    if not clips:
        print(f"No complete clips (mp4 + pgn + calibration.json) in {args.dir}. See its README.")
        return 2
    results = [
        run_clip(
            v,
            load_pgn_moves(v.with_suffix(".pgn")),
            Calibration.load(v.with_suffix(".calibration.json")),
        )
        for v in clips
    ]
    summary = summarize(results)
    print("== ChessLens eval (REAL footage, no operator resync) ==")
    print(f"clips: {summary['clips']}  truth moves: {summary['truth_moves']}")
    print(f"correct-prefix accuracy: {summary['prefix_accuracy']:.1%}")
    print(f"fully correct clips: {summary['fully_correct_clips']}/{summary['clips']}")
    print(f"uncertain events: {summary['uncertain_events']}")
    for r in results:
        print(
            f"  {r.name:<28} prefix {r.correct_prefix}/{r.truth_moves}"
            f"  accepted {r.accepted}  uncertain {r.uncertain}"
        )
    if args.json:
        args.json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
