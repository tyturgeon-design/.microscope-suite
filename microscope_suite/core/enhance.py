"""Microscope cleaning pipeline.

Order: flat-field -> channel alignment -> rotate/flip -> circular crop ->
background flatten -> colour-fringe suppression -> denoise -> white balance /
levels / CLAHE -> gamma/contrast/brightness -> saturation -> sharpen.

Everything is resolution-independent except pixel shifts, which are in
full-resolution pixels and multiplied by `scale` (preview/full-res ratio).
"""
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class CleanParams:
    # geometry / crop
    rot90: int = 0
    flip_h: bool = False
    crop_on: bool = True
    radius: float = 0.95      # fraction of half the short side
    cx: float = 0.0           # centre offset, fraction of width
    cy: float = 0.0
    # lateral chromatic aberration (shifts relative to green, full-res px)
    r_dx: float = 0.0
    r_dy: float = 0.0
    b_dx: float = 0.0
    b_dy: float = 0.0
    r_scale: float = 1.0      # radial magnification about centre
    b_scale: float = 1.0
    # colour-fringe suppressor
    defringe: float = 0.0     # 0 = off .. 1 = full desaturation
    fringe_sat: float = 110   # only pixels more saturated than this
    fringe_width: float = 4   # fringe search width, px
    fringe_dark: float = 110  # V below this counts as a dark boundary
    # illumination
    flat_strength: float = 1.0
    bg_flatten: float = 0.0
    # tone / colour
    auto_wb: bool = False
    auto_levels: bool = False
    clahe: bool = False
    gamma: float = 1.0
    contrast: float = 1.0
    brightness: float = 0.0
    saturation: float = 1.0
    # detail
    denoise: float = 0.0
    sharpen: float = 0.0
    sharpen_radius: float = 1.0
    # internal: preview scale relative to full-res (not a user setting)
    scale: float = 1.0


def _u8(a):
    return np.clip(a, 0, 255).astype(np.uint8)


# --- illumination ----------------------------------------------------------
def flat_field(img, flat, strength):
    """Divide by a blank-slide reference to cancel dust spots and uneven light."""
    if flat.shape[:2] != img.shape[:2]:
        flat = cv2.resize(flat, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_AREA)
    ref = cv2.GaussianBlur(flat.astype(np.float32), (0, 0), 1.5) + 1.0
    mean = ref[::4, ::4].reshape(-1, 3).mean(0)
    gain = np.clip(mean / ref, 0.25, 4.0)
    return _u8(img.astype(np.float32) * (1 + strength * (gain - 1)))


def flatten_background(img, strength, mask=None):
    """Reference-free illumination correction (divide by a heavily blurred copy)."""
    h, w = img.shape[:2]
    k = max(1, max(h, w) // 256)
    small = cv2.resize(img, (max(2, w // k), max(2, h // k)), interpolation=cv2.INTER_AREA)
    f = small.astype(np.float32)
    sigma = max(small.shape[:2]) * 0.08
    if mask is not None:
        m = cv2.resize((mask > 0).astype(np.float32), (small.shape[1], small.shape[0]))
        bg = cv2.GaussianBlur(f * m[..., None], (0, 0), sigma) / np.maximum(
            cv2.GaussianBlur(m, (0, 0), sigma)[..., None], 1e-3)
        target = f[m > 0.5].mean(0) if (m > 0.5).any() else f.reshape(-1, 3).mean(0)
    else:
        bg = cv2.GaussianBlur(f, (0, 0), sigma)
        target = f.reshape(-1, 3).mean(0)
    gain = np.clip(target / np.maximum(bg, 1.0), 0.3, 3.0)
    gain = cv2.resize(gain, (w, h), interpolation=cv2.INTER_LINEAR)
    return _u8(img.astype(np.float32) * (1 + strength * (gain - 1)))


# --- chromatic aberration ---------------------------------------------------
def align_channels(img, p):
    if not (p.r_dx or p.r_dy or p.b_dx or p.b_dy or p.r_scale != 1 or p.b_scale != 1):
        return img
    h, w = img.shape[:2]
    cx, cy = (w - 1) / 2, (h - 1) / 2
    b, g, r = cv2.split(img)

    def warp(ch, dx, dy, s):
        if not (dx or dy or s != 1):
            return ch
        M = np.float32([[s, 0, (1 - s) * cx + dx * p.scale],
                        [0, s, (1 - s) * cy + dy * p.scale]])
        return cv2.warpAffine(ch, M, (w, h), flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_REPLICATE)

    return cv2.merge([warp(b, p.b_dx, p.b_dy, p.b_scale), g,
                      warp(r, p.r_dx, p.r_dy, p.r_scale)])


def estimate_ca(img):
    """Auto-estimate (r_dx, r_dy, b_dx, b_dy) in px by phase-correlating edge maps."""
    h, w = img.shape[:2]
    s = min(h, w, 1024)
    y0, x0 = (h - s) // 2, (w - s) // 2
    roi = img[y0:y0 + s, x0:x0 + s]

    def edges(c):
        c = c.astype(np.float32)
        return cv2.magnitude(cv2.Sobel(c, cv2.CV_32F, 1, 0), cv2.Sobel(c, cv2.CV_32F, 0, 1))

    b, g, r = (edges(c) for c in cv2.split(roi))
    win = cv2.createHanningWindow((s, s), cv2.CV_32F)
    (rx, ry), _ = cv2.phaseCorrelate(g, r, win)
    (bx, by), _ = cv2.phaseCorrelate(g, b, win)
    return -rx, -ry, -bx, -by


# --- colour fringes ---------------------------------------------------------
def suppress_fringes(img, p, mask=None):
    """Desaturate thin, saturated yellow/cyan/magenta halos hugging dark edges."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    width = max(1, int(round(p.fringe_width * p.scale)))
    k = 2 * width + 1
    ell = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))

    dark = v < p.fringe_dark
    if mask is not None:
        dark &= mask > 0
    near = cv2.dilate(dark.astype(np.uint8), ell) > 0

    hue_ok = ((h >= 15) & (h <= 38)) | ((h >= 78) & (h <= 102)) | ((h >= 138) & (h <= 172))
    cand = ((s > p.fringe_sat) & hue_ok & near).astype(np.uint8)
    thin = cand & ~cv2.morphologyEx(cand, cv2.MORPH_OPEN, ell).astype(bool)  # drop big blobs
    m = cv2.GaussianBlur(thin.astype(np.float32), (0, 0), max(0.8, width / 3))
    s2 = s.astype(np.float32) * (1 - p.defringe * np.clip(m * 1.5, 0, 1))
    return cv2.cvtColor(cv2.merge([h, _u8(s2), v]), cv2.COLOR_HSV2BGR)


# --- crop helpers -----------------------------------------------------------
def _circle_crop(img, p):
    h, w = img.shape[:2]
    r = max(2, int(p.radius * min(h, w) / 2))
    cx, cy = int(w / 2 + p.cx * w), int(h / 2 + p.cy * h)
    mask = np.zeros((h, w), np.uint8)
    cv2.circle(mask, (cx, cy), r, 255, -1)
    x0, x1 = max(0, cx - r), min(w, cx + r)
    y0, y1 = max(0, cy - r), min(h, cy + r)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return img, None
    return img[y0:y1, x0:x1].copy(), mask[y0:y1, x0:x1]


def detect_vignette(img):
    """Find the lit circle on a phone-microscope frame -> (radius, cx_off, cy_off) or None."""
    h, w = img.shape[:2]
    k = min(1.0, 600 / max(h, w))
    small = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    g = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    _, bw = cv2.threshold(g, 20, 255, cv2.THRESH_BINARY)
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    cnts, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(c) < 0.05 * g.size:
        return None
    (x, y), r = cv2.minEnclosingCircle(c)
    sh, sw = g.shape
    return (r / (min(sh, sw) / 2) * 0.97, x / sw - 0.5, y / sh - 0.5)


# --- main pipeline ----------------------------------------------------------
def apply_clean(img, p, flat=None):
    out = img
    if flat is not None and p.flat_strength > 0:
        out = flat_field(out, flat, p.flat_strength)
    out = align_channels(out, p)
    if p.flip_h:
        out = cv2.flip(out, 1)
    if p.rot90 % 4:
        out = np.ascontiguousarray(np.rot90(out, -(p.rot90 % 4)))

    mask = None
    if p.crop_on:
        out, mask = _circle_crop(out, p)
    else:
        out = out.copy()

    if p.bg_flatten > 0:
        out = flatten_background(out, p.bg_flatten, mask)
    if p.defringe > 0:
        out = suppress_fringes(out, p, mask)
    if p.denoise > 0:
        out = cv2.bilateralFilter(out, 7, p.denoise, max(2.0, 3 * p.scale))

    sel = out[::4, ::4] if mask is None else out[::4, ::4][mask[::4, ::4] > 0]
    sel = sel.reshape(-1, 3)
    if p.auto_wb and sel.size:
        p95 = np.maximum(np.percentile(sel, 95, axis=0), 1)
        gains = np.clip(p95.max() / p95, 0.5, 2.0).astype(np.float32)
        out = _u8(out.astype(np.float32) * gains)
    if p.auto_levels and sel.size:
        lum = sel.mean(1)
        lo, hi = np.percentile(lum, (0.5, 99.5))
        if hi - lo > 8:
            lut = _u8((np.arange(256, dtype=np.float32) - lo) * 255 / (hi - lo))
            out = cv2.LUT(out, lut)
    if p.clahe:
        lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB)
        lab[..., 0] = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(lab[..., 0])
        out = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    if p.contrast != 1.0 or p.brightness != 0 or p.gamma != 1.0:
        x = np.arange(256, dtype=np.float32)
        y = np.clip((x - 128) * p.contrast + 128 + p.brightness, 0, 255) / 255
        out = cv2.LUT(out, _u8(255 * y ** (1 / max(p.gamma, 0.05))))

    if p.saturation != 1.0:
        hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[..., 1] = np.clip(hsv[..., 1] * p.saturation, 0, 255)
        out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    if p.sharpen > 0:
        sigma = max(0.4, p.sharpen_radius * max(out.shape[:2]) / 1000)
        out = cv2.addWeighted(out, 1 + p.sharpen, cv2.GaussianBlur(out, (0, 0), sigma),
                              -p.sharpen, 0)

    if mask is not None:
        out[mask == 0] = 0
    return out
