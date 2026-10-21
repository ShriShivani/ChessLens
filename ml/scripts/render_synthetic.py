"""Render synthetic labelled crops from random games.

Run:  python -m ml.scripts.render_synthetic --out ml/data/synthetic --games 12 --positions 8

Each game gets one `Style` ("session"); several games share a style so the split script can
keep a whole style out of training. Output: one .npz per game (see ml/data.py).
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import chess
import numpy as np

from ml.common import DEFAULT_INPUT, board_labels, square_crops
from ml.data import save_game
from ml.synthetic import Style, render_warped
from tests.synth import random_game


def positions(moves: list[chess.Move], count: int, rng: random.Random) -> list[chess.Board]:
    """`count` boards spread through the game, always including the starting position."""
    board = chess.Board()
    boards = [board.copy()]
    for m in moves:
        board.push(m)
        boards.append(board.copy())
    picks = sorted(rng.sample(range(1, len(boards)), min(count - 1, len(boards) - 1)))
    return [boards[0]] + [boards[i] for i in picks]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("ml/data/synthetic"))
    ap.add_argument("--games", type=int, default=12)
    ap.add_argument("--positions", type=int, default=8, help="boards rendered per game")
    ap.add_argument("--plies", type=int, default=60)
    ap.add_argument("--styles", type=int, default=4, help="number of lighting/colour sessions")
    ap.add_argument("--size", type=int, default=DEFAULT_INPUT)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    styles = [Style.random(random.Random(args.seed * 1000 + s)) for s in range(args.styles)]
    for g in range(args.games):
        rng = random.Random(args.seed * 100_000 + g)
        session = f"style{g % args.styles}"
        moves = random_game(args.seed * 100_000 + g, args.plies)
        crops, labels = [], []
        for board in positions(moves, args.positions, rng):
            crops.append(
                square_crops(render_warped(board, styles[g % args.styles], rng), args.size)
            )
            labels.append(board_labels(board))
        name = f"synthetic_{g:03d}"
        save_game(
            args.out / f"{name}.npz",
            np.concatenate(crops),
            np.concatenate(labels),
            game=name,
            session=session,
            source="synthetic",
        )
        print(f"wrote {name} ({len(crops)} boards, {session})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
