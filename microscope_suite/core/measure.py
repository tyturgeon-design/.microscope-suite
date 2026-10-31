"""Distance maths and scale-bar stamping."""
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from core.utils import bgr_to_pil


def pixel_distance(p1, p2):
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])


def nice_length(target):
    """Largest 1/2/5 x 10^n value that is <= target."""
    base = 10 ** math.floor(math.log10(target))
    best = base
    for m in (1, 2, 5):
        if m * base <= target:
            best = m * base
    return best


def format_length(um):
    if um >= 1000:
        return f"{um / 1000:g} mm"
    if um < 1:
        return f"{um * 1000:g} nm"
    return f"{um:g} \u00b5m"


def _font(size):
    for name in ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf", "Helvetica.ttc"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def stamp_scale_bar(img, um_per_px, corner="bottom-right", width_frac=0.2):
    """Return a copy of img (BGR) with a labelled scale bar in the chosen bottom corner."""
    h, w = img.shape[:2]
    length_um = nice_length(width_frac * w * um_per_px)
    bar_px = max(2, int(round(length_um / um_per_px)))
    label = format_length(length_um)

    font = _font(max(14, int(h * 0.03)))
    thick = max(4, int(h * 0.007))
    margin = int(min(h, w) * 0.04)
    pad = int(thick * 1.5)

    base = bgr_to_pil(img).convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    tb = d.textbbox((0, 0), label, font=font)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]

    box_w = max(bar_px, tw) + 2 * pad
    box_h = th + thick + 3 * pad
    if corner == "bottom-left":
        x0 = margin
        x1 = x0 + box_w
    else:
        x1 = w - margin
        x0 = x1 - box_w
    y1 = h - margin
    y0 = y1 - box_h

    d.rectangle((x0, y0, x1, y1), fill=(0, 0, 0, 150))
    cx = (x0 + x1) // 2
    d.text((cx - tw // 2 - tb[0], y0 + pad - tb[1]), label, font=font, fill=(255, 255, 255, 255))
    by1 = y1 - pad
    d.rectangle((cx - bar_px // 2, by1 - thick, cx - bar_px // 2 + bar_px, by1),
                fill=(255, 255, 255, 255))

    out = Image.alpha_composite(base, overlay).convert("RGB")
    return cv2.cvtColor(np.asarray(out), cv2.COLOR_RGB2BGR)
