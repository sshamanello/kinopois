"""Frame renderer for Pinterest-ready movie poster creatives."""

from __future__ import annotations

import hashlib
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


def render_framed_poster(src_path: Path, dst_path: Path, seed_key: str) -> Path:
    """Render eye-catching unique frame around poster and save JPG."""
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    base = Image.open(src_path).convert("RGB").resize((1000, 1500), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (1000, 1500), (244, 240, 229))

    seed = int(hashlib.sha1(seed_key.encode("utf-8")).hexdigest()[:8], 16)
    rng = random.Random(seed)

    shadow = Image.new("RGBA", (860, 1320), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.rounded_rectangle((0, 0, 860, 1320), radius=28, fill=(0, 0, 0, 125))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    canvas.paste(shadow, (74, 72), shadow)

    poster = base.resize((830, 1285), Image.Resampling.LANCZOS)
    canvas.paste(poster, (85, 90))

    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((42, 42, 958, 1458), radius=30, outline=(50, 47, 43), width=8)
    draw.rounded_rectangle((74, 79, 926, 1426), radius=25, outline=(233, 227, 211), width=20)

    palette = [
        (231, 88, 71),
        (61, 135, 214),
        (246, 182, 60),
        (59, 161, 127),
        (143, 94, 190),
        (232, 118, 44),
    ]
    c1 = palette[rng.randrange(len(palette))]
    c2 = palette[rng.randrange(len(palette))]
    strip_w = 16 + rng.randint(0, 10)
    draw.rounded_rectangle((58, 120, 58 + strip_w, 1380), radius=8, fill=c1)
    draw.rounded_rectangle((942 - strip_w, 180, 942, 1320), radius=8, fill=c2)

    for _ in range(120):
        x = rng.randint(48, 952)
        y = rng.randint(48, 1452)
        a = rng.randint(12, 30)
        r = rng.randint(1, 2)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, a))

    canvas.save(dst_path, quality=93)
    return dst_path
