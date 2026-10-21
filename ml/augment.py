"""Training-time augmentation for square crops (RGB uint8 in, RGB uint8 out).

Colour augmentation is limited to brightness, contrast, noise and per-channel gain close to 1.
It never inverts or hue-shifts, because that could turn a white piece into a black one.
"""

from __future__ import annotations

import cv2
import numpy as np


def augment(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    h, w = img.shape[:2]
    out = img.astype(np.float32)

    # Geometry: shift and scale about +-8%, small rotation, small perspective wobble.
    scale = 1 + rng.uniform(-0.08, 0.08)
    angle = rng.uniform(-8, 8)
    tx, ty = rng.uniform(-0.08, 0.08, 2) * (w, h)
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, scale)
    m[:, 2] += (tx, ty)
    out = cv2.warpAffine(out, m, (w, h), borderMode=cv2.BORDER_REFLECT)
    if rng.random() < 0.5:
        jitter = rng.uniform(-0.04, 0.04, (4, 2)) * (w, h)
        src = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
        out = cv2.warpPerspective(
            out,
            cv2.getPerspectiveTransform(src, src + jitter.astype(np.float32)),
            (w, h),
            borderMode=cv2.BORDER_REFLECT,
        )

    # Light: brightness, contrast, per-channel gain, soft shadow gradient.
    out = out * rng.uniform(0.7, 1.3) + rng.uniform(-25, 25)
    out = (out - 128) * rng.uniform(0.8, 1.25) + 128
    out = out * rng.uniform(0.95, 1.05, 3)
    if rng.random() < 0.4:
        gradient = np.linspace(rng.uniform(0.6, 1.0), 1.0, w, dtype=np.float32)
        if rng.random() < 0.5:
            gradient = gradient[::-1]
        out = out * gradient[None, :, None]

    # Sensor: blur and noise.
    if rng.random() < 0.4:
        k = int(rng.choice([3, 5]))
        out = cv2.GaussianBlur(out, (k, k), 0)
    out = out + rng.normal(0, rng.uniform(0, 6), out.shape)

    # Random erasing of a small patch.
    if rng.random() < 0.25:
        eh, ew = int(h * rng.uniform(0.1, 0.3)), int(w * rng.uniform(0.1, 0.3))
        y, x = int(rng.integers(0, h - eh)), int(rng.integers(0, w - ew))
        out[y : y + eh, x : x + ew] = rng.uniform(0, 255, 3)

    return np.clip(out, 0, 255).astype(np.uint8)
