"""Image I/O helpers (no GUI dependencies)."""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp", ".webm"}


def is_video(path):
    return Path(path).suffix.lower() in VIDEO_SUFFIXES


def pil_to_bgr(im):
    im = ImageOps.exif_transpose(im).convert("RGB")
    return cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)


def bgr_to_pil(arr):
    return Image.fromarray(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB))


def load_image(path):
    with Image.open(path) as im:
        return pil_to_bgr(im)


def save_image(arr, path):
    """Save at full resolution with high-quality settings chosen by extension."""
    ext = Path(path).suffix.lower()
    kw = {}
    if ext in (".jpg", ".jpeg"):
        kw = dict(quality=98, subsampling=0)
    elif ext == ".png":
        kw = dict(compress_level=3)
    elif ext in (".tif", ".tiff"):
        kw = dict(compression="tiff_lzw")
    bgr_to_pil(arr).save(str(path), **kw)


def limit_pixels(img, max_pixels):
    """Downscale so h*w <= max_pixels. Returns (image, scale_factor)."""
    h, w = img.shape[:2]
    if not max_pixels or h * w <= max_pixels:
        return img, 1.0
    k = (max_pixels / (h * w)) ** 0.5
    return cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA), k
