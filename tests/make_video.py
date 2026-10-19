"""Write a synthetic game to an mp4 plus its calibration JSON.

Run:  python -m tests.make_video tests/games/italian_castling.pgn tests/fixtures/italian
Produces <prefix>.mp4 and <prefix>.calibration.json (git-ignored, regenerate any time).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from tests.synth import FRAME_H, FRAME_W, SynthConfig, load_pgn_moves, play


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("pgn", type=Path)
    ap.add_argument("prefix", type=Path)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--white-side", default="bottom", choices=["bottom", "left", "top", "right"])
    args = ap.parse_args(argv)

    cfg = SynthConfig(seed=args.seed, white_side=args.white_side)
    game = play(load_pgn_moves(args.pgn), cfg)
    args.prefix.parent.mkdir(parents=True, exist_ok=True)
    out = cv2.VideoWriter(
        str(args.prefix.with_suffix(".mp4")),
        cv2.VideoWriter_fourcc(*"mp4v"),
        cfg.fps,
        (FRAME_W, FRAME_H),
    )
    for frame, _, _ in game.frames:
        out.write(frame)
    out.release()
    game.calibration.save(args.prefix.with_suffix(".calibration.json"))
    print(f"wrote {args.prefix}.mp4 and {args.prefix}.calibration.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
