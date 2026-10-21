"""ONNX inference on a warped board. Depends on onnxruntime and numpy only (no torch)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort

from ml.common import join_probs, square_crops


def _softmax(z: np.ndarray, temperature: float) -> np.ndarray:
    z = z / temperature
    z = z - z.max(1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(1, keepdims=True)


class SquareClassifier:
    """predict(warped) -> (64, 13) class probabilities, indexed by chess square."""

    def __init__(self, onnx_path: str | Path) -> None:
        path = Path(onnx_path)
        self.session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        meta = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        self.size = int(meta["input_size"])
        self.t_occ = float(meta.get("temperature_occ", 1.0))
        self.t_typ = float(meta.get("temperature_typ", 1.0))

    def predict_crops(self, crops: np.ndarray) -> np.ndarray:
        x = np.ascontiguousarray(crops.transpose(0, 3, 1, 2)).astype(np.float32) / 255.0
        occ, typ = self.session.run(None, {"x": x})
        return join_probs(_softmax(occ, self.t_occ), _softmax(typ, self.t_typ))

    def predict(self, warped: np.ndarray) -> np.ndarray:
        return self.predict_crops(square_crops(warped, self.size))

    def latency_ms(self, warped: np.ndarray, runs: int = 20) -> float:
        """Median wall time for one full board (cropping included)."""
        self.predict(warped)  # warm-up
        times = []
        for _ in range(runs):
            t0 = time.perf_counter()
            self.predict(warped)
            times.append((time.perf_counter() - t0) * 1000)
        return float(np.median(times))
