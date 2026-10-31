"""Tab 2: full microscope clean-up panel with live preview."""
import json
import os
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np
from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp, sp

from core.enhance import CleanParams, apply_clean, detect_vignette, estimate_ca
from core.utils import is_video, limit_pixels, load_image
from core.video import open_video
from ui import platform_io
from ui.base import TabScreen
from ui.state import settings
from ui.tasks import LatestWorker, on_ui, run_bg
from ui.widgets import (Btn, Collapsible, HistView, SliderRow, ToggleRow, WrapLabel,
                        ask_text, choose_from, show_message)

PREVIEW_MAX = 1100
D = CleanParams()

# (field, label, min, max, format)
CROP = [("radius", "Circle radius", 0.2, 1.2, "{:.2f}"),
        ("cx", "Centre X offset", -0.4, 0.4, "{:+.3f}"),
        ("cy", "Centre Y offset", -0.4, 0.4, "{:+.3f}")]
CA = [("r_dx", "Red shift X", -8, 8, "{:+.2f} px"), ("r_dy", "Red shift Y", -8, 8, "{:+.2f} px"),
      ("b_dx", "Blue shift X", -8, 8, "{:+.2f} px"), ("b_dy", "Blue shift Y", -8, 8, "{:+.2f} px"),
      ("r_scale", "Red radial scale", 0.99, 1.01, "{:.4f}"),
      ("b_scale", "Blue radial scale", 0.99, 1.01, "{:.4f}")]
FRINGE = [("defringe", "Suppression strength", 0, 1, "{:.2f}"),
          ("fringe_sat", "Saturation threshold", 0, 255, "{:.0f}"),
          ("fringe_width", "Fringe width (px)", 1, 15, "{:.0f}"),
          ("fringe_dark", "Dark-edge level", 20, 200, "{:.0f}")]
TONE = [("gamma", "Gamma", 0.4, 2.5, "{:.2f}"), ("contrast", "Contrast", 0.5, 2.5, "{:.2f}"),
        ("brightness", "Brightness", -100, 100, "{:+.0f}"),
        ("saturation", "Saturation", 0, 2, "{:.2f}")]
DETAIL = [("denoise", "Denoise (edge-preserving)", 0, 40, "{:.0f}"),
          ("sharpen", "Sharpen amount", 0, 3, "{:.2f}"),
          ("sharpen_radius", "Sharpen radius", 0.4, 5, "{:.2f}")]


def _hist(img):
    sub = img[::2, ::2]
    out = []
    for ch in range(3):
        h = cv2.calcHist([sub], [ch], None, [64], [0, 256]).ravel()
        h[0] = 0   # ignore black crop mask
        out.append(h / max(h.max(), 1))
    return out


class CleanerScreen(TabScreen):
    def __init__(self, send_to_measure=None, **kw):
        super().__init__(**kw)
        self.send_to_measure = send_to_measure
        self.source = self.proxy = self.video = None
        self.flat = self.flat_proxy = None
        self.k, self.rot, self.before = 1.0, 0, False
        self.sliders, self.checks = {}, {}
        self._vjob = None
        self.worker = LatestWorker(self._render, self._show)

        self.tool("Open", self.open_file, primary=True)
        self.tool("Save", self.save)
        self.toggle_tool("Before", self._set_before)
        self.tool("Measure", self.send)
        self.add_expand_tool()

        # --- file & tools
        f = Collapsible("File & tools", expanded=True)
        self.frame_row = SliderRow("Video frame", 0, 1, 0, "{:.0f}", self._schedule_frame, step=1)
        self.file_box = f
        f.add(Btn("Batch process photos\u2026", self.batch))
        f.add(Btn("Save preset\u2026", self.save_preset))
        f.add(Btn("Load preset\u2026", self.load_preset))
        f.add(Btn("Reset all", self.reset))
        self.controls.add(f)

        # --- crop
        c = Collapsible("Crop & orientation")
        self._check(c, "crop_on", "Crop circular vignette")
        c.add(Btn("Auto-detect circle", self.auto_circle))
        self._sliders(c, CROP)
        c.add(Btn("Rotate 90\u00b0", self.rotate))
        self._check(c, "flip_h", "Flip horizontally")
        self.controls.add(c)

        # --- CA
        c = Collapsible("Channel alignment (lateral CA)")
        c.add(WrapLabel(text="Shifts Red/Blue relative to Green to cancel colour fringing.",
                        font_size=sp(12)))
        c.add(Btn("Auto-align channels", self.auto_ca))
        self._sliders(c, CA)
        self.controls.add(c)

        # --- fringes
        c = Collapsible("Colour-fringe suppressor")
        c.add(WrapLabel(text="Desaturates thin yellow/cyan/magenta halos beside dark edges.",
                        font_size=sp(12)))
        self._sliders(c, FRINGE)
        self.controls.add(c)

        # --- illumination
        c = Collapsible("Illumination / flat-field")
        c.add(Btn("Load blank-slide reference\u2026", self.load_flat))
        c.add(Btn("Clear reference", self.clear_flat))
        self.flat_lbl = c.add(WrapLabel(text="No flat-field loaded", font_size=sp(12)))
        self._sliders(c, [("flat_strength", "Flat-field strength", 0, 1, "{:.2f}"),
                          ("bg_flatten", "Background flatten (no ref)", 0, 1, "{:.2f}")])
        self.controls.add(c)

        # --- tone
        c = Collapsible("Tone & colour")
        self._check(c, "auto_wb", "Auto white balance")
        self._check(c, "auto_levels", "Auto levels")
        self._check(c, "clahe", "Local contrast (CLAHE)")
        self._sliders(c, TONE)
        self.controls.add(c)

        # --- detail
        c = Collapsible("Detail")
        self._sliders(c, DETAIL)
        self.controls.add(c)

        # --- histogram
        c = Collapsible("Histogram")
        self.hist = HistView(size_hint_y=None, height=dp(90))
        c.add(self.hist)
        self.controls.add(c)
        self.set_status("Open a photo or video.")

    # --- builders
    def _check(self, sec, field, text):
        self.checks[field] = sec.add(ToggleRow(text, getattr(D, field), self._schedule))

    def _sliders(self, sec, specs):
        for field, label, lo, hi, fmt in specs:
            self.sliders[field] = sec.add(
                SliderRow(label, lo, hi, getattr(D, field), fmt, self._schedule))

    def params(self, scale=1.0):
        d = {k: s.value for k, s in self.sliders.items()}
        d.update({k: c.value for k, c in self.checks.items()})
        return CleanParams(rot90=self.rot, scale=scale, **d)

    # --- loading
    def open_file(self):
        platform_io.pick("media", self._picked)

    def _picked(self, paths):
        if not paths:
            return
        path = paths[0]

        def load():
            if is_video(path):
                v = open_video(path)
                f0 = v.read_frame(0)
                if f0 is None:
                    raise IOError("Could not read first frame.")
                return "video", v, f0
            return "image", None, load_image(path)

        def done(res, err):
            if err:
                show_message("Can't open file", str(err))
                return
            kind, v, img = res
            self._close_video()
            name = os.path.basename(path)
            if kind == "video":
                self.video = v
                self.frame_row.set_range(0, max(1, v.count - 1))
                self.frame_row.set(0)
                if self.frame_row.parent is None:
                    self.file_box.body.add_widget(self.frame_row, index=len(self.file_box.body.children))
                self.set_status(f"{name} (video, {v.count} frames)")
            else:
                self._hide_frame_row()
                self.set_status(name)
            self._set_source(img)
        run_bg(load, done)

    def set_image(self, bgr, label="Image from another tab"):
        self._close_video()
        self._hide_frame_row()
        self.set_status(label)
        self._set_source(bgr)

    def _hide_frame_row(self):
        if self.frame_row.parent is not None:
            self.frame_row.parent.remove_widget(self.frame_row)

    def _close_video(self):
        if self.video:
            self.video.close()
            self.video = None

    def _set_source(self, bgr, reset=True):
        self.source = bgr
        h, w = bgr.shape[:2]
        self.k = min(1.0, PREVIEW_MAX / max(h, w))
        self.proxy = bgr if self.k == 1.0 else cv2.resize(
            bgr, None, fx=self.k, fy=self.k, interpolation=cv2.INTER_AREA)
        if reset:
            self.view.texture = None   # new image -> reset zoom
        self._make_flat_proxy()
        self._schedule()

    def _make_flat_proxy(self):
        if self.flat is None or self.proxy is None:
            self.flat_proxy = None
        else:
            h, w = self.proxy.shape[:2]
            self.flat_proxy = cv2.resize(self.flat, (w, h), interpolation=cv2.INTER_AREA)

    def _schedule_frame(self):
        if self._vjob:
            self._vjob.cancel()
        self._vjob = Clock.schedule_once(lambda dt: self._load_frame(), 0.25)

    def _load_frame(self):
        v, idx = self.video, int(self.frame_row.value)
        if v:
            run_bg(lambda: v.read_frame(idx),
                   lambda f, e: self._set_source(f, reset=False) if f is not None else None)

    # --- live preview
    def _schedule(self, *_):
        if self.proxy is not None:
            self.worker.submit(self.proxy, self.flat_proxy, self.params(self.k), self.before)

    def _render(self, proxy, flat, params, before):
        out = proxy if before else apply_clean(proxy, params, flat)
        return out, _hist(out)

    def _show(self, res):
        out, hist = res
        self.view.set_image(out)
        self.hist.set_data(hist)

    def _set_before(self, on):
        self.before = on
        self._schedule()

    # --- auto tools
    def auto_circle(self):
        if self.source is None:
            return
        src = self.source

        def done(res, err):
            if res is None:
                show_message("Auto-detect", "Couldn't find a clear circular vignette.")
                return
            self.checks["crop_on"].set(True)
            for key, v in zip(("radius", "cx", "cy"), res):
                self.sliders[key].set(v)
        run_bg(lambda: detect_vignette(src), done)

    def auto_ca(self):
        if self.source is None:
            return
        src = self.source

        def done(vals, err):
            if err:
                return
            for key, v in zip(("r_dx", "r_dy", "b_dx", "b_dy"), vals):
                self.sliders[key].set(float(np.clip(v, -8, 8)))
        run_bg(lambda: estimate_ca(src), done)

    def rotate(self):
        self.rot = (self.rot + 1) % 4
        self._schedule()

    def reset(self):
        for k, s in self.sliders.items():
            s.set(getattr(D, k))
        for k, c in self.checks.items():
            c.set(getattr(D, k))
        self.rot = 0
        self._schedule()

    # --- flat-field
    def load_flat(self):
        platform_io.pick("image", self._flat_picked)

    def _flat_picked(self, paths):
        if not paths:
            return

        def done(img, err):
            if err:
                show_message("Error", str(err))
                return
            self.flat = img
            self.flat_lbl.text = f"Flat: {os.path.basename(paths[0])}"
            self._make_flat_proxy()
            self._schedule()
        run_bg(lambda: load_image(paths[0]), done)

    def clear_flat(self):
        self.flat = self.flat_proxy = None
        self.flat_lbl.text = "No flat-field loaded"
        self._schedule()

    # --- presets (stored in the app's private folder)
    def _preset_dir(self):
        d = Path(App.get_running_app().user_data_dir) / "presets"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_preset(self):
        def got(name):
            if not name:
                return
            d = asdict(self.params())
            d.pop("scale")
            (self._preset_dir() / f"{name}.json").write_text(json.dumps(d, indent=2))
            show_message("Preset saved", name)
        ask_text("Preset name", got, hint="e.g. 40x brightfield")

    def load_preset(self):
        names = sorted(p.stem for p in self._preset_dir().glob("*.json"))
        if not names:
            show_message("No presets", "Save a preset first.")
            return

        def got(name):
            d = json.loads((self._preset_dir() / f"{name}.json").read_text())
            for k, v in d.items():
                if k in self.sliders:
                    self.sliders[k].set(v)
                elif k in self.checks:
                    self.checks[k].set(bool(v))
                elif k == "rot90":
                    self.rot = int(v) % 4
            self._schedule()
        choose_from("Load preset", names, got)

    # --- export
    def _prepare_full(self):
        img, k = limit_pixels(self.source, settings.max_pixels())
        return img, self.params(k), self.flat

    def save(self):
        if self.source is None:
            show_message("Nothing to save", "Open a photo or video first.")
            return
        img, p, flat = self._prepare_full()
        self.set_status("Exporting\u2026")
        run_bg(lambda: platform_io.export_bgr(apply_clean(img, p, flat), "clean"),
               lambda r, e: (self.set_status("Done"), show_message("Saved" if not e else "Error",
                                                                   r or str(e))))

    def send(self):
        if self.source is None or not self.send_to_measure:
            return
        img, p, flat = self._prepare_full()
        run_bg(lambda: apply_clean(img, p, flat),
               lambda out, e: self.send_to_measure(out) if not e else show_message("Error", str(e)))

    def batch(self):
        platform_io.pick("image", self._batch_picked, multiple=True)

    def _batch_picked(self, paths):
        if not paths:
            return
        p_base, flat, maxpx = self.params(), self.flat, settings.max_pixels()

        def work():
            fails = 0
            for n, path in enumerate(paths, 1):
                try:
                    img, k = limit_pixels(load_image(path), maxpx)
                    p = CleanParams(**{**asdict(p_base), "scale": k})
                    platform_io.export_bgr(apply_clean(img, p, flat), Path(path).stem + "_clean")
                except Exception:
                    fails += 1
                on_ui(self.set_status, f"Batch: {n}/{len(paths)}")
            return len(paths) - fails, fails

        def done(res, err):
            ok, fails = res if res else (0, len(paths))
            self.set_status("Batch complete")
            show_message("Batch complete", f"Processed {ok} of {len(paths)} images."
                         + (f"\n{fails} failed." if fails else ""))
        run_bg(work, done)
