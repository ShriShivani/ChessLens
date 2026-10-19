import numpy as np

from edge.stability import StabilityGate


def frame(v: int) -> np.ndarray:
    return np.full((200, 200), v, dtype=np.uint8)


def test_fires_once_after_still_period():
    gate = StabilityGate(still_seconds=0.5)
    fired = [gate.update(frame(100), t / 10) for t in range(20)]
    assert fired.count(True) == 1
    assert fired.index(True) == 5  # first frame at t=0 starts the clock; fires at t=0.5


def test_motion_resets_and_refires():
    gate = StabilityGate(still_seconds=0.3)
    for t in range(6):
        gate.update(frame(100), t / 10)
    rng = np.random.default_rng(0)
    moving = rng.integers(0, 255, (200, 200), dtype=np.uint8)
    assert not gate.update(moving, 0.6)
    fired = [gate.update(moving, 0.7 + t / 10) for t in range(6)]
    assert fired.count(True) == 1


def test_ignores_global_brightness_flicker():
    gate = StabilityGate(still_seconds=0.3)
    img = np.tile(np.arange(200, dtype=np.uint8), (200, 1)) // 2 + 50
    fired = [gate.update((img * (1 + 0.01 * (t % 2))).astype(np.uint8), t / 10) for t in range(10)]
    assert any(fired)
