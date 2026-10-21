"""Train/validation/test splits by game and session, never by crop.

Consecutive frames of one game are nearly identical, so a random crop-level split leaks test
data into training. Whole groups (a session if known, otherwise a game) go to one split.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence

SPLITS = ("train", "val", "test")


def split_groups(
    games: Sequence[str],
    sessions: Mapping[str, str] | None = None,
    fractions: tuple[float, float, float] = (0.7, 0.15, 0.15),
    seed: int = 0,
) -> dict[str, str]:
    """Return {game_id: "train" | "val" | "test"}.

    Games that share a session (same lighting and board) always land in the same split, so
    the test set is a genuinely unseen setup whenever more than one session exists.
    """
    if abs(sum(fractions) - 1.0) > 1e-6:
        raise ValueError("fractions must sum to 1")
    groups: dict[str, list[str]] = {}
    for game in sorted(set(games)):
        key = sessions[game] if sessions and game in sessions else game
        groups.setdefault(key, []).append(game)

    keys = sorted(groups)
    random.Random(seed).shuffle(keys)
    n = len(keys)
    n_test = max(1, round(n * fractions[2])) if n >= 3 else 0
    n_val = max(1, round(n * fractions[1])) if n >= 3 else 0
    n_val = min(n_val, max(0, n - n_test - 1))
    assignment: dict[str, str] = {}
    for i, key in enumerate(keys):
        split = "test" if i < n_test else "val" if i < n_test + n_val else "train"
        for game in groups[key]:
            assignment[game] = split
    return assignment


def assert_no_leakage(
    assignment: Mapping[str, str], sessions: Mapping[str, str] | None = None
) -> None:
    """Raise if a session (or game) appears in more than one split."""
    seen: dict[str, str] = {}
    for game, split in assignment.items():
        key = sessions[game] if sessions and game in sessions else game
        if seen.setdefault(key, split) != split:
            raise AssertionError(f"{key!r} appears in both {seen[key]} and {split}")
