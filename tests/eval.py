"""Accuracy evaluation of the edge pipeline on synthetic games.

Run:  python -m tests.eval [--random N] [--plies P] [--no-occlusion] [--json OUT]

Scoring is per move. After each move is judged, the pipeline is resynced to the truth
(as an operator would), so one miss does not cascade into every later move.
Outcomes: correct (auto-accepted, right), uncertain (flagged, nothing guessed),
missed (no event), wrong (a different move was auto-accepted).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import chess

from edge.pipeline import Pipeline
from tests.synth import SynthConfig, categorize, load_pgn_moves, play, random_game

ROOT = Path(__file__).parent
THRESHOLDS = ROOT / "eval_thresholds.json"
SIDES = ("bottom", "top", "left", "right")
OUTCOMES = ("correct", "uncertain", "missed", "wrong")


@dataclass
class GameResult:
    name: str
    outcomes: list[tuple[str, str]] = field(default_factory=list)  # (category, outcome)

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def correct(self) -> int:
        return sum(1 for _, o in self.outcomes if o == "correct")


def _resync(pipe: Pipeline, truth: list[chess.Move], upto: int) -> None:
    """Make the pipeline's game equal truth[:upto], like an operator using undo/force."""
    while pipe.board.move_stack != truth[: len(pipe.board.move_stack)]:
        pipe.undo()
    for move in truth[len(pipe.board.move_stack) : upto]:
        pipe.force_move(move.uci())


def run_game(name: str, moves: list[chess.Move], cfg: SynthConfig) -> GameResult:
    synth = play(moves, cfg)
    pipe = Pipeline(synth.calibration)
    result = GameResult(name)
    categories: list[str] = []
    board = chess.Board()
    for move in moves:
        categories.append(categorize(board, move))
        board.push(move)

    judged = 0
    started = 0
    flagged = False

    def judge() -> None:
        nonlocal judged, flagged
        stack = pipe.board.move_stack
        if stack == moves[: judged + 1]:
            outcome = "correct"
        elif stack == moves[:judged]:
            outcome = "uncertain" if flagged else "missed"
        else:
            outcome = "wrong"
        result.outcomes.append((categories[judged], outcome))
        if outcome != "correct":
            _resync(pipe, moves, judged + 1)
        judged += 1
        flagged = False

    in_move = False
    for frame, t, moving in synth.frames:
        if moving and not in_move:
            # A new move begins, so the previous move's hold phase is over: judge it now.
            if started > 0:
                judge()
            started += 1
        in_move = moving
        for event in pipe.process_frame(frame, t):
            if event.kind == "uncertain":
                flagged = True
    judge()
    return result


def summarize(results: list[GameResult]) -> dict:
    overall: Counter[str] = Counter()
    by_cat: dict[str, Counter[str]] = defaultdict(Counter)
    for r in results:
        for cat, outcome in r.outcomes:
            overall[outcome] += 1
            by_cat[cat][outcome] += 1
    total = sum(overall.values())

    def block(c: Counter[str]) -> dict:
        n = sum(c.values())
        return {
            "moves": n,
            **{o: c[o] for o in OUTCOMES},
            "accuracy": c["correct"] / n if n else 0.0,
        }

    return {
        "moves": total,
        "accuracy": overall["correct"] / total if total else 0.0,
        "wrong_rate": overall["wrong"] / total if total else 0.0,
        "outcomes": {o: overall[o] for o in OUTCOMES},
        "games": len(results),
        "games_fully_correct": sum(1 for r in results if r.correct == r.total),
        "per_category": {c: block(v) for c, v in sorted(by_cat.items())},
        "per_game": {r.name: {"moves": r.total, "accuracy": r.correct / r.total} for r in results},
    }


def build_games(n_random: int, plies: int) -> list[tuple[str, list[chess.Move]]]:
    games = [(p.stem, load_pgn_moves(p)) for p in sorted((ROOT / "games").glob("*.pgn"))]
    games += [(f"random_{s}", random_game(s, plies)) for s in range(n_random)]
    return games


def print_report(summary: dict, label: str) -> None:
    print(f"== ChessLens eval ({label}) ==")
    print(f"games: {summary['games']}  moves: {summary['moves']}")
    print(f"move accuracy: {summary['accuracy']:.1%}")
    print(f"wrong (silent) rate: {summary['wrong_rate']:.2%}")
    print(f"outcomes: {summary['outcomes']}")
    print(f"games with every move correct: {summary['games_fully_correct']}/{summary['games']}")
    print("per category:")
    for cat, b in summary["per_category"].items():
        print(
            f"  {cat:<11} {b['correct']:>4}/{b['moves']:<4} {b['accuracy']:.1%}  "
            f"(uncertain {b['uncertain']}, missed {b['missed']}, wrong {b['wrong']})"
        )
    print("per game:")
    for name, g in summary["per_game"].items():
        print(f"  {name:<24} {g['accuracy']:.1%} of {g['moves']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--random", type=int, default=6, help="number of random games")
    ap.add_argument("--plies", type=int, default=30, help="plies per random game")
    ap.add_argument("--no-occlusion", action="store_true", help="disable simulated hands")
    ap.add_argument("--noise", type=float, default=3.0, help="sensor noise sigma (gray levels)")
    ap.add_argument("--corner-jitter", type=float, default=2.0, help="corner click error (px)")
    ap.add_argument("--lighting", type=float, default=0.04, help="per-move lighting drift")
    ap.add_argument("--json", type=Path, help="write the summary to this file")
    ap.add_argument("--no-threshold", action="store_true", help="report only; never fail")
    args = ap.parse_args(argv)

    results: list[GameResult] = []
    for i, (name, moves) in enumerate(build_games(args.random, args.plies)):
        cfg = SynthConfig(
            seed=i,
            white_side=SIDES[i % len(SIDES)],
            occlusion=not args.no_occlusion,
            noise_sigma=args.noise,
            corner_jitter=args.corner_jitter,
            lighting_jitter=args.lighting,
        )
        results.append(run_game(name, moves, cfg))
        print(f"  ran {name}: {results[-1].correct}/{results[-1].total}", file=sys.stderr)

    summary = summarize(results)
    label = "synthetic" + (", no occlusion" if args.no_occlusion else ", with hand occlusion")
    print_report(summary, label)
    if args.json:
        args.json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if args.no_threshold:
        return 0
    limits = json.loads(THRESHOLDS.read_text(encoding="utf-8"))
    failed = []
    if summary["accuracy"] < limits["min_move_accuracy"]:
        failed.append(f"accuracy {summary['accuracy']:.3f} < {limits['min_move_accuracy']}")
    if summary["wrong_rate"] > limits["max_wrong_rate"]:
        failed.append(f"wrong rate {summary['wrong_rate']:.4f} > {limits['max_wrong_rate']}")
    if failed:
        print("FAIL: " + "; ".join(failed))
        return 1
    print("PASS: thresholds met")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
