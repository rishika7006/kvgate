#!/usr/bin/env python3
"""Generate N distinct, detailed 1024x1024 PNGs for the multimodal benchmark.
Each image is visually unique (varied shapes/colors/seed) so its vision-token KV is
distinct — that's what creates real per-image KV pressure. Usage: python gen_images.py [N]
"""
import os
import sys

from PIL import Image, ImageDraw

N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "images")
OUT = os.environ.get("IMAGES_DIR", OUT)
os.makedirs(OUT, exist_ok=True)


def rng(seed):
    s = seed
    while True:
        s = (1103515245 * s + 12345) & 0x7FFFFFFF
        yield s


for i in range(N):
    g = rng(i * 7919 + 1)
    img = Image.new("RGB", (1024, 1024), (next(g) % 64, next(g) % 64, next(g) % 64))
    d = ImageDraw.Draw(img)
    for _ in range(220):  # lots of detail -> many distinct vision tokens
        x0, y0 = next(g) % 1024, next(g) % 1024
        x1, y1 = next(g) % 1024, next(g) % 1024
        color = (next(g) % 256, next(g) % 256, next(g) % 256)
        if next(g) % 3 == 0:
            d.ellipse([min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)], fill=color)
        elif next(g) % 3 == 1:
            d.rectangle([min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)], outline=color, width=3)
        else:
            d.line([x0, y0, x1, y1], fill=color, width=2)
    img.save(os.path.join(OUT, f"img_{i:03d}.png"))

print(f"wrote {N} images to {OUT}")
