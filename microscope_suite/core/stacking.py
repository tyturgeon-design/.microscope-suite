"""Focus stacking: Laplacian-variance scoring + per-pixel sharpest-region merge."""
import math
from dataclasses import dataclass

import cv2
import numpy as np

from core.video import open_video


@dataclass
class StackResult:
    image: np.ndarray
    scores: list   # [(frame_index, laplacian_variance), ...]
    kept: list     # frame indices used in the merge


def laplacian_variance(gray):
    """Global focus measure for one frame (higher = sharper)."""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def local_sharpness(gray):
    """Smoothed per-pixel focus map used to pick the sharpest source per region."""
    g = cv2.GaussianBlur(gray, (3, 3), 0)
    lap = np.abs(cv2.Laplacian(g, cv2.CV_32F, ksize=3))
    return cv2.GaussianBlur(lap, (0, 0), sigmaX=4)


def align_translation(ref_gray, frame, gray):
    """Cancel small hand-held shifts / focus breathing with ECC (translation only)."""
    s = 0.25
    r = cv2.resize(ref_gray, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    g = cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    warp = np.eye(2, 3, dtype=np.float32)
    crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, 1e-4)
    try:
        _, warp = cv2.findTransformECC(r, g, warp, cv2.MOTION_TRANSLATION, crit, None, 5)
    except cv2.error:
        return frame
    warp[:, 2] /= s
    h, w = frame.shape[:2]
    return cv2.warpAffine(frame, warp, (w, h),
                          flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_REPLICATE)


def stack_video(path, step=1, min_rel=0.0, align=False, progress=None, cancel=None):
    """Two passes: (1) score every frame, (2) merge frames above the threshold.

    progress(phase, done, total) is called as work proceeds; cancel is a
    threading.Event. Returns StackResult, or None if cancelled.
    """
    vid = open_video(path)
    try:
        return _stack(vid, step, min_rel, align, progress, cancel)
    finally:
        vid.close()


def _stack(vid, step, min_rel, align, progress, cancel):
    total = math.ceil(vid.count / step) if vid.count > 0 else 0

    scores = []
    for n, (i, f) in enumerate(vid.frames(step), 1):
        if cancel is not None and cancel.is_set():
            return None
        scores.append((i, laplacian_variance(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY))))
        if progress:
            progress("Scoring frames", n, max(total, n))
    if not scores:
        raise ValueError("No frames could be read from the video.")

    top = max(s for _, s in scores)
    keep = {i for i, s in scores if s >= min_rel * top}

    best_img = best_sharp = ref_gray = None
    done = 0
    for i, frame in vid.frames(step):
        if cancel is not None and cancel.is_set():
            return None
        if i not in keep:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if ref_gray is None:
            ref_gray = gray
        elif align:
            frame = align_translation(ref_gray, frame, gray)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        sharp = local_sharpness(gray)
        if best_img is None:
            best_img, best_sharp = frame.copy(), sharp
        else:
            m = sharp > best_sharp
            best_img[m] = frame[m]
            np.maximum(best_sharp, sharp, out=best_sharp)
        done += 1
        if progress:
            progress("Merging frames", done, len(keep))
    return StackResult(best_img, scores, sorted(keep))
