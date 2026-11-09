"""Turn the avatar into ASCII art once (assets/ascii.txt). Run locally: python scripts/make_ascii.py [image]

Dense areas get density glyphs, thin strokes get a glyph that follows the stroke
direction (| / - \\), so the line art of the avatar stays readable.
"""
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent.parent
COLS, ROWS = 64, 32
RAMP = " .:-=+*#%@"


def main(src: str) -> None:
    im = ImageOps.autocontrast(Image.open(src).convert("L"), cutoff=1)
    cw, ch = im.width / COLS, im.height / ROWS
    small = im.filter(ImageFilter.GaussianBlur(1.5))
    a = np.asarray(small, dtype=float) / 255
    gy, gx = np.gradient(a)
    lines = []
    for r in range(ROWS):
        row = ""
        for c in range(COLS):
            dx = (c + 0.5) / COLS - 0.5
            dy = (r + 0.5) / ROWS - 0.5
            if dx * dx + dy * dy > 0.245:
                row += " "
                continue
            y0, y1 = int(r * ch), int((r + 1) * ch)
            x0, x1 = int(c * cw), int((c + 1) * cw)
            ink = 1 - a[y0:y1, x0:x1].mean()
            if ink < 0.12:
                row += " "
                continue
            if ink > 0.6:
                row += RAMP[min(len(RAMP) - 1, int(ink * len(RAMP)))]
                continue
            # structure tensor -> dominant stroke direction in this cell
            sx, sy = gx[y0:y1, x0:x1], gy[y0:y1, x0:x1]
            jxx, jyy, jxy = (sx * sx).sum(), (sy * sy).sum(), (sx * sy).sum()
            coherence = math.hypot(jxx - jyy, 2 * jxy) / (jxx + jyy + 1e-9)
            if coherence < 0.25:
                row += RAMP[min(len(RAMP) - 1, int(ink * len(RAMP)))]
                continue
            grad_angle = 0.5 * math.atan2(2 * jxy, jxx - jyy)  # gradient direction
            stroke = math.degrees(grad_angle + math.pi / 2) % 180  # stroke runs across it
            # image y points down, so 45 deg on screen is "\"
            row += "-" if stroke < 22.5 or stroke >= 157.5 else "\\" if stroke < 67.5 else "|" if stroke < 112.5 else "/"
        lines.append(row.rstrip())
    (ROOT / "assets").mkdir(exist_ok=True)
    (ROOT / "assets" / "ascii.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "assets" / "avatar.png"))
