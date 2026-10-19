"""Stability gate: only hand over frames once the board has been still for a while."""

from __future__ import annotations

import cv2
import numpy as np

SMALL = 100


def _small_gray(warped: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY) if warped.ndim == 3 else warped
    small = cv2.resize(gray, (SMALL, SMALL), interpolation=cv2.INTER_AREA)
    return small.astype(np.float32)


class StabilityGate:
    """Tracks frame-to-frame motion; fires once per still period."""

    def __init__(self, still_seconds: float = 0.7, motion_threshold: float = 1.5) -> None:
        self.still_seconds = still_seconds
        self.motion_threshold = motion_threshold
        self._prev: np.ndarray | None = None
        self._still_since: float | None = None
        self._fired = False

    def reset(self) -> None:
        self._prev = None
        self._still_since = None
        self._fired = False

    def update(self, warped: np.ndarray, t: float) -> bool:
        """Feed a warped frame; True exactly once when the board has settled."""
        cur = _small_gray(warped)
        prev, self._prev = self._prev, cur
        if prev is None:
            self._still_since = t
            return False
        # Ignore global brightness flicker by matching medians before comparing.
        gain = (np.median(prev) + 1e-3) / (np.median(cur) + 1e-3)
        motion = float(np.mean(np.abs(cur * gain - prev)))
        if motion > self.motion_threshold:
            self._still_since = t
            self._fired = False
            return False
        if self._still_since is None:
            self._still_since = t
        if not self._fired and t - self._still_since >= self.still_seconds:
            self._fired = True
            return True
        return False
