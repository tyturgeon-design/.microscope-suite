"""Tab 3: tap two points, calibrate, convert px -> um, stamp a scale bar."""
import os

import cv2
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from core.measure import format_length, pixel_distance, stamp_scale_bar
from core.utils import load_image
from ui import platform_io
from ui.base import TabScreen
from ui.tasks import LatestWorker, run_bg
from ui.widgets import (Btn, Collapsible, SliderRow, ToggleRow, WrapLabel, ask_text,
                        show_message)

PROXY_MAX = 2400


class MeasureScreen(TabScreen):
    def __init__(self, **kw):
        super().__init__(on_tap=self._tap, **kw)
        self.image = self.proxy = None
        self.k = 1.0
        self.points = []
        self.upp = None            # micrometres per source pixel
        self.worker = LatestWorker(self._render, self._show)

        self.tool("Open", self.open_image, primary=True)
        self.tool("Save", self.save)
        self.tool("Undo", self.undo)
        self.tool("Clear", self.clear)
        self.add_expand_tool()

        self.readout = self.controls.add(WrapLabel(text="Tap two points on the image.",
                                                   font_size=sp(16)))
        cal = Collapsible("Calibration", expanded=True)
        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(4))
        row.add_widget(Label(text="\u00b5m / pixel", font_size=sp(14), size_hint_x=0.4))
        self.upp_in = TextInput(multiline=False, input_filter="float", font_size=sp(17),
                                hint_text="e.g. 0.85")
        row.add_widget(self.upp_in)
        row.add_widget(Btn("Set", self.apply_scale, size_hint_x=0.25))
        cal.add(row)
        cal.add(Btn("Calibrate from measured line", self.calibrate))
        cal.add(WrapLabel(
            text="Tip: photograph a stage micrometer or ruler, measure a known length "
                 "with two taps, then use the button above.", font_size=sp(12)))
        self.controls.add(cal)

        bar = Collapsible("Scale bar", expanded=True)
        self.show = bar.add(ToggleRow("Preview scale bar", True, self._refresh))
        self.corner = Spinner(text="bottom-right", values=("bottom-right", "bottom-left"),
                              size_hint_y=None, height=dp(44), font_size=sp(15))
        self.corner.bind(text=lambda *_: self._refresh())
        bar.add(self.corner)
        self.width_pct = bar.add(SliderRow("Bar length (% of width)", 5, 40, 20, "{:.0f}%",
                                           self._refresh, step=1))
        self.controls.add(bar)
        self.set_status("Open an image (or send one from the Clean tab).")

    # --- loading
    def open_image(self):
        platform_io.pick("image", self._picked)

    def _picked(self, paths):
        if not paths:
            return
        run_bg(lambda: load_image(paths[0]),
               lambda img, err: self.set_image(img, os.path.basename(paths[0])) if not err
               else show_message("Error", str(err)))

    def set_image(self, bgr, label="Image from another tab"):
        self.image = bgr
        h, w = bgr.shape[:2]
        self.k = min(1.0, PROXY_MAX / max(h, w))
        self.proxy = bgr if self.k == 1.0 else cv2.resize(
            bgr, None, fx=self.k, fy=self.k, interpolation=cv2.INTER_AREA)
        self.points = []
        self.view.points = []
        self.view.texture = None   # force view reset for new image
        self.set_status(f"{label} - {w} x {h} px")
        self._readout()
        self._refresh()

    # --- measuring
    def _tap(self, ix, iy):
        if len(self.points) >= 2:
            self.points = []
        self.points.append((ix, iy))
        self._sync_points()

    def undo(self):
        if self.points:
            self.points.pop()
            self._sync_points()

    def clear(self):
        self.points = []
        self._sync_points()

    def _sync_points(self):
        self.view.points = list(self.points)
        self.view.redraw()
        self._readout()

    def _readout(self):
        if len(self.points) < 2:
            self.readout.text = (f"Scale: {self.upp:.4f} \u00b5m/px\n" if self.upp else "") + \
                "Tap two points on the image."
            return
        d = pixel_distance(*self.points)
        real = format_length(d * self.upp) if self.upp else "set calibration first"
        self.readout.text = f"Distance: {d:,.1f} px\nReal size: {real}"

    def apply_scale(self):
        try:
            v = float(self.upp_in.text)
            if v <= 0:
                raise ValueError
        except ValueError:
            show_message("Invalid", "Enter a positive number of \u00b5m per pixel.")
            return
        self.upp = v
        self._readout()
        self._refresh()

    def calibrate(self):
        if len(self.points) < 2:
            show_message("Calibrate", "Tap two points on an object of known size first.")
            return
        d = pixel_distance(*self.points)

        def got(txt):
            try:
                known = float(txt)
                if known <= 0:
                    raise ValueError
            except ValueError:
                return
            self.upp_in.text = f"{known / d:.5f}"
            self.apply_scale()
        ask_text("Real length of this line (\u00b5m)", got, hint="micrometres", numeric=True)

    # --- display (stamp on a proxy for speed; save stamps full-res)
    def _refresh(self, *_):
        if self.proxy is not None:
            self.worker.submit(self.proxy, self.k, self.upp, self.show.value,
                               self.corner.text, self.width_pct.value / 100)

    def _render(self, proxy, k, upp, show, corner, frac):
        if show and upp:
            return stamp_scale_bar(proxy, upp / k, corner, frac)
        return proxy

    def _show(self, out):
        h, w = self.image.shape[:2]
        self.view.points = list(self.points)
        self.view.set_image(out, source_wh=(w, h))

    # --- save
    def save(self):
        if self.image is None:
            show_message("Nothing to save", "Open an image first.")
            return
        if not self.upp:
            show_message("No calibration", "Set \u00b5m per pixel before stamping a scale bar.")
            return
        img, upp, corner, frac = self.image, self.upp, self.corner.text, self.width_pct.value / 100
        run_bg(lambda: platform_io.export_bgr(stamp_scale_bar(img, upp, corner, frac), "scalebar"),
               lambda r, e: show_message("Saved" if not e else "Error", r or str(e)))
