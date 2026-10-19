#!/usr/bin/env python3
"""Make the AI-generated building textures truly seamless (tileable).

The raw images in ``docs/textures/`` are AI-generated and not guaranteed to
tile.  This script turns each one into an exact 1024x1024 seamless tile:

1. For directions with a detectable structural pitch (brick courses, plank
   gaps, metal ridges) a window of an exact whole number of periods is cut.
   Cutting on a period boundary makes the wrap seam structurally continuous.
2. For stochastic directions (wood grain along X, rust along Y, concrete) the
   two edges are cross-faded with a smooth ramp, the classic "make seamless"
   technique.

Run from the repository root:

    python tools/make_seamless.py
"""

from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image

SIZE = 1024
TEXTURE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "textures"
)

# name -> (x_pitch, y_pitch, fade_x, fade_y)
#   pitch in pixels of the repeating structure, or None for stochastic axes.
#   fade is the width of the cross-fade band applied on that axis.
CONFIG = {
    "brick_wall": (154, 102, 0, 0),
    "wood_plank": (None, 102, 48, 0),
    "metal_corrugated": (32, None, 0, 20),
    "concrete_wall": (None, None, 48, 48),
}

# Albedo grading applied after tiling.  AI renders tend to come back too bright
# and too flat for a physically plausible diffuse map.  Each entry is
# (target mean, contrast gain): contrast is stretched around the image mean,
# then the mean is shifted onto the target so the asset never renders as
# blown-out white under neutral HDRI lighting.
GRADE = {
    "brick_wall": (0.36, 1.15),
    "wood_plank": (0.38, 1.10),
    "metal_corrugated": (0.38, 1.15),
    "concrete_wall": (0.62, 2.00),
}


def _phase_search(arr: np.ndarray, axis: int, span: int) -> int:
    """Pick the start offset of a ``span``-long window with the best edge match."""
    n = arr.shape[axis]
    best, best_cost = 0, float("inf")
    first = np.take(arr, 0, axis=axis).astype(np.float32)
    for off in range(0, n, 4):
        idx = np.arange(off, off + span) % n
        win = np.take(arr, idx, axis=axis)
        last = np.take(win, -1, axis=axis).astype(np.float32)
        cost = float(np.abs(first - last).mean())
        if cost < best_cost:
            best, best_cost = off, cost
    return best


def _crop_periodic(arr: np.ndarray, pitch: int, axis: int, target: int) -> np.ndarray:
    """Cut a window holding a whole number of ``pitch`` periods (wrap-aware)."""
    n = arr.shape[axis]
    count = max(1, round(target / pitch))
    span = count * pitch
    start = _phase_search(arr, axis, min(span, n))
    idx = np.arange(start, start + span) % n
    return np.take(arr, idx, axis=axis)


def _cross_fade(arr: np.ndarray, width: int, axis: int) -> np.ndarray:
    """Cross-fade the first ``width`` samples of ``axis`` with the last ones."""
    if width <= 0:
        return arr
    out = arr.astype(np.float32)
    a = np.linspace(0.0, 1.0, width, dtype=np.float32)[:, None]
    if axis == 1:
        left = arr[:, :width, :].astype(np.float32)
        right = arr[:, -width:, :].astype(np.float32)
        out[:, :width, :] = a[None, :, :] * left + (1.0 - a[None, :, :]) * right
    else:
        top = arr[:width, :, :].astype(np.float32)
        bottom = arr[-width:, :, :].astype(np.float32)
        out[:width, :, :] = a[:, :, None] * top + (1.0 - a[:, :, None]) * bottom
    return np.clip(out, 0, 255).astype(np.uint8)


def add_mottling(arr: np.ndarray, strength: float, seed: int = 7) -> np.ndarray:
    """Modulate brightness with seamless multi-octave noise.

    Flat AI albedos look like plastic; a little low-frequency tonal variation
    makes them read as a real surface.  The noise is generated in the
    frequency domain so it tiles perfectly by construction.
    """
    h, w, _ = arr.shape
    rng = np.random.default_rng(seed)
    field = np.zeros((h, w), dtype=np.float32)
    for octave, weight in ((2, 1.0), (4, 0.5), (8, 0.25), (16, 0.12)):
        noise = rng.normal(size=(octave, octave)).astype(np.float32)
        # Upsample seamlessly by tiling the coarse grid, then smooth.
        up = np.kron(noise, np.ones((h // octave, w // octave), dtype=np.float32))
        up = np.roll(up, (h // (2 * octave), w // (2 * octave)), axis=(0, 1))
        k = max(3, h // octave)
        kernel = np.outer(np.hanning(k), np.hanning(k)).astype(np.float32)
        kernel /= kernel.sum()
        field += weight * _freq_blur(up, kernel)
    field /= np.abs(field).max()
    scale = 1.0 + strength * field[..., None]
    return np.clip(arr.astype(np.float32) * scale, 0, 255).astype(np.uint8)


def _freq_blur(img: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Wrap-around (circular) convolution - keeps the tile seamless."""
    h, w = img.shape
    k = np.zeros((h, w), dtype=np.float32)
    kh, kw = kernel.shape
    k[:kh, :kw] = kernel
    k = np.roll(k, (-(kh // 2), -(kw // 2)), axis=(0, 1))
    return np.real(np.fft.ifft2(np.fft.fft2(img) * np.fft.fft2(k))).astype(np.float32)


def make_seamless(name: str) -> tuple[int, int]:
    path = os.path.join(TEXTURE_DIR, f"{name}.png")
    img = Image.open(path).convert("RGB")
    arr = np.asarray(img).astype(np.uint8)
    x_pitch, y_pitch, fade_x, fade_y = CONFIG[name]

    # Metal is not square at source: tile/upscale after the periodic crop.
    if x_pitch:
        arr = _crop_periodic(arr, x_pitch, axis=1, target=SIZE)
    if y_pitch:
        arr = _crop_periodic(arr, y_pitch, axis=0, target=SIZE)

    if fade_x:
        arr = _cross_fade(arr, fade_x, axis=1)
    if fade_y:
        arr = _cross_fade(arr, fade_y, axis=0)

    out = Image.fromarray(arr, "RGB").resize((SIZE, SIZE), Image.LANCZOS)
    out_arr = np.asarray(out).astype(np.uint8)

    # Final light cross-fade so the resampled edges stay continuous.
    out_arr = _cross_fade(out_arr, max(fade_x, 8), axis=1)
    out_arr = _cross_fade(out_arr, max(fade_y, 8), axis=0)

    if name == "concrete_wall":
        out_arr = add_mottling(out_arr, 0.10)

    target, gain = GRADE[name]
    graded = (out_arr.astype(np.float32) / 255.0 - 0.5) * gain + 0.5
    graded += target - float(graded.mean())
    out_arr = (np.clip(graded, 0.0, 1.0) * 255.0).astype(np.uint8)

    Image.fromarray(out_arr, "RGB").save(path, optimize=True)
    return out.size


def seam_ratio(arr: np.ndarray) -> tuple[float, float]:
    """Wrap-seam mismatch relative to the typical interior neighbour difference."""
    a = arr.astype(np.float32)
    sx = float(np.abs(a[:, 0] - a[:, -1]).mean())
    sy = float(np.abs(a[0] - a[-1]).mean())
    ix = max(float(np.abs(np.diff(a, axis=1)).mean()), 1e-6)
    iy = max(float(np.abs(np.diff(a, axis=0)).mean()), 1e-6)
    return sx / ix, sy / iy


def main() -> int:
    if not os.path.isdir(TEXTURE_DIR):
        print(f"missing texture directory: {TEXTURE_DIR}", file=sys.stderr)
        return 1
    for name in CONFIG:
        size = make_seamless(name)
        rx, ry = seam_ratio(np.asarray(Image.open(os.path.join(TEXTURE_DIR, name + ".png"))))
        print(f"{name:20s} {size[0]}x{size[1]}  seam_x={rx:.2f}x  seam_y={ry:.2f}x interior")
    return 0


if __name__ == "__main__":
    sys.exit(main())
