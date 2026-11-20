"""The sample pen masks in pc/web/masks/: made here from formulas and a fixed random seed, so they
are ReDrawable's own work (MIT, like the rest). Needs numpy and Pillow; the app itself doesn't.

    python installer/make_sample_masks.py

White lets the pen through, black blocks it, grey holds it back in between (as any mask image).
Square images; the app fits a mask to cover the tablet screen as it sits, so the edges of a
square fall off a 3:4 screen and the shapes stay inside the middle.
"""
import json
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

S = 960  # pixels across; the tablet keeps 720 x 720 cells over the screen
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pc", "web", "masks")
rng = np.random.default_rng(20261118)
yy, xx = np.mgrid[0:S, 0:S].astype(np.float32) / S  # 0..1


def fractal(octaves, base, falloff=0.55):
    """Smooth value noise in octaves: blobs of size S/base and finer layers on top, 0..1."""
    out, amp, total = np.zeros((S, S), np.float32), 1.0, 0.0
    for o in range(octaves):
        n = base * 2 ** o
        small = Image.fromarray((rng.random((n, n)) * 255).astype(np.uint8))
        out += amp * np.asarray(small.resize((S, S), Image.BICUBIC), np.float32) / 255
        total += amp
        amp *= falloff
    out /= total
    return (out - out.min()) / (out.max() - out.min())


def shade(v, lo, hi=1.0):
    """0..1 to a grey image whose darkest is lo and lightest hi (1 = white)."""
    return Image.fromarray(np.clip((lo + (hi - lo) * v) * 255, 0, 255).astype(np.uint8), "L")


def stencil(draw_fn, blur=1.5):
    """A white shape on black, drawn 4x large and scaled down for clean edges."""
    big = Image.new("L", (S * 4, S * 4), 0)
    draw_fn(ImageDraw.Draw(big), S * 4)
    return big.resize((S, S), Image.LANCZOS).filter(ImageFilter.GaussianBlur(blur))


def star(d, n, points=5, inner=0.42):
    c, r = n / 2, n * 0.33
    pts = []
    for i in range(points * 2):
        a = -np.pi / 2 + i * np.pi / points
        k = r if i % 2 == 0 else r * inner
        pts.append((c + k * np.cos(a), c + 0.04 * n + k * np.sin(a)))
    d.polygon(pts, fill=255)


def heart(d, n):
    t = np.linspace(0, 2 * np.pi, 400)
    x = 16 * np.sin(t) ** 3
    y = -(13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t))
    k = n * 0.30 / 17
    d.polygon([(n / 2 + k * a, n / 2 + k * b) for a, b in zip(x, y)], fill=255)


SAMPLES = [
    # id, name (at most 24 letters), how it's made
    ("rough-paper", "Rough paper", lambda: shade(0.65 * fractal(4, 80, 0.7) + 0.35 * fractal(3, 8, 0.5), 0.4)),
    ("coarse-grain", "Coarse grain", lambda: shade(np.clip(fractal(4, 40, 0.5) * 1.6 - 0.3, 0, 1), 0.1)),
    ("corrugation", "Corrugation", lambda: shade(0.5 + 0.5 * np.cos(2 * np.pi * 24 * yy), 0.15)),
    ("diagonal-hatch", "Diagonal hatch",
     lambda: shade((((xx + yy) * 40) % 1 > 0.28).astype(np.float32), 0.0).filter(ImageFilter.GaussianBlur(0.8))),
    ("canvas-weave", "Canvas weave",
     lambda: shade(0.5 + 0.25 * np.cos(2 * np.pi * 60 * xx) * np.sign(np.cos(2 * np.pi * 30 * yy))
                   + 0.25 * np.cos(2 * np.pi * 60 * yy) * np.sign(np.cos(2 * np.pi * 30 * xx)), 0.35)),
    ("halftone", "Halftone dots",
     lambda: shade((np.hypot((xx * 48) % 1 - 0.5, (yy * 48) % 1 - 0.5) > 0.32).astype(np.float32), 0.0)
     .filter(ImageFilter.GaussianBlur(0.8))),
    ("checker", "Checkerboard",
     lambda: shade(((np.floor(xx * 12) + np.floor(yy * 12)) % 2).astype(np.float32), 0.0)),
    ("fade", "Fade, left to right", lambda: shade(xx, 0.0)),
    ("vignette", "Soft edges",
     lambda: shade(np.clip((0.48 - np.hypot(xx - 0.5, yy - 0.5)) / 0.2, 0, 1), 0.0)),
    ("circle", "Circle",
     lambda: stencil(lambda d, n: d.ellipse((n * 0.18, n * 0.18, n * 0.82, n * 0.82), fill=255))),
    ("square", "Rounded square",
     lambda: stencil(lambda d, n: d.rounded_rectangle((n * 0.2, n * 0.2, n * 0.8, n * 0.8), radius=n * 0.06, fill=255))),
    ("triangle", "Triangle",
     lambda: stencil(lambda d, n: d.polygon([(n / 2, n * 0.18), (n * 0.84, n * 0.78), (n * 0.16, n * 0.78)], fill=255))),
    ("star", "Star", lambda: stencil(star)),
    ("heart", "Heart", lambda: stencil(heart)),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    index = []
    for sid, name, make in SAMPLES:
        assert len(name) <= 24, name
        img = make()
        assert img.mode == "L" and img.size == (S, S), sid
        img.save(os.path.join(OUT, sid + ".png"), optimize=True)
        index.append({"id": sid, "name": name})
    with open(os.path.join(OUT, "index.json"), "w") as f:
        json.dump(index, f, indent=1)
        f.write("\n")
    print(len(index), "masks in", os.path.normpath(OUT))


if __name__ == "__main__":
    main()
