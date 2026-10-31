"""Tab 1: video -> focus-stacked composite."""
import os
import threading

from kivy.metrics import dp, sp
from kivy.uix.progressbar import ProgressBar

from core.stacking import stack_video
from core.video import open_video
from ui import platform_io
from ui.base import TabScreen
from ui.tasks import on_ui, run_bg
from ui.widgets import (Collapsible, PlotView, SliderRow, ToggleRow, WrapLabel,
                        show_message)


class StackerScreen(TabScreen):
    def __init__(self, send_to_cleaner=None, **kw):
        super().__init__(**kw)
        self.send_to_cleaner = send_to_cleaner
        self.path = None
        self.result = None
        self.running = False
        self.cancel = threading.Event()

        self.tool("Open video", self.open_video, primary=True)
        self.run_btn = self.tool("Run stack", self.run)
        self.tool("Save", self.save)
        self.tool("Clean", self.send)
        self.add_expand_tool()

        c = Collapsible("Stack settings", expanded=True)
        self.step = c.add(SliderRow("Use every Nth frame", 1, 30, 1, "{:.0f}", step=1))
        self.minpct = c.add(SliderRow("Discard frames below (% of best)", 0, 90, 20, "{:.0f}%", step=1))
        self.align = c.add(ToggleRow("Align frames (slower, fixes shake)"))
        self.controls.add(c)

        self.bar = ProgressBar(max=100, size_hint_y=None, height=dp(16))
        self.controls.add(self.bar)
        self.progress_lbl = self.controls.add(WrapLabel(text=""))
        self.controls.add(WrapLabel(text="Sharpness per frame (orange = used in merge):"))
        self.plot = PlotView(size_hint_y=None, height=dp(90))
        self.controls.add(self.plot)
        self.controls.add(WrapLabel(
            text="Tip: record while slowly turning the fine-focus knob, with the phone "
                 "locked on a stand. Lock exposure/focus mode if your camera app allows.",
            font_size=sp(12)))
        self.set_status("Open a video recorded while fine-focusing.")

    # --- load
    def open_video(self):
        platform_io.pick("video", self._picked)

    def _picked(self, paths):
        if not paths:
            return
        path = paths[0]

        def load():
            v = open_video(path)
            try:
                return v.count, v.width, v.height, v.fps, v.backend, v.read_frame(0)
            finally:
                v.close()

        def done(res, err):
            if err:
                show_message("Can't open video", str(err))
                return
            n, w, h, fps, backend, first = res
            self.path, self.result = path, None
            self.set_status(f"{os.path.basename(path)}\n{n} frames, {w}x{h}, {fps:.1f} fps "
                            f"[{backend}]")
            self.view.set_image(first)
            self.plot.set_data([], [])
            self.bar.value = 0
            self.progress_lbl.text = ""

        run_bg(load, done)

    # --- run
    def run(self):
        if self.running:
            self.cancel.set()
            return
        if not self.path:
            show_message("No video", "Open a video first.")
            return
        self.cancel.clear()
        self.running = True
        self.run_btn.text = "Cancel"
        path, step = self.path, int(round(self.step.value))
        min_rel, align = self.minpct.value / 100, self.align.value

        def progress(phase, d, t):
            if d % 3 == 0 or d == t:
                on_ui(self._progress, phase, d, t)

        run_bg(lambda: stack_video(path, step, min_rel, align, progress, self.cancel),
               self._done)

    def _progress(self, phase, d, t):
        pct = 50 * d / max(t, 1) + (0 if phase.startswith("Scor") else 50)
        self.bar.value = min(pct, 100)
        self.progress_lbl.text = f"{phase}: {d}/{t}"

    def _done(self, res, err):
        self.running = False
        self.run_btn.text = "Run stack"
        if err:
            show_message("Stacking failed", str(err))
            return
        if res is None:
            self.progress_lbl.text = "Cancelled"
            return
        self.result = res
        self.bar.value = 100
        self.progress_lbl.text = f"Done: merged {len(res.kept)} of {len(res.scores)} frames"
        self.view.set_image(res.image)
        kept = set(res.kept)
        self.plot.set_data([s for _, s in res.scores], [i in kept for i, _ in res.scores])

    # --- output
    def save(self):
        if not self.result:
            show_message("Nothing to save", "Run the stack first.")
            return
        img = self.result.image
        run_bg(lambda: platform_io.export_bgr(img, "stack"),
               lambda r, e: show_message("Saved" if not e else "Error", r or str(e)))

    def send(self):
        if self.result and self.send_to_cleaner:
            self.send_to_cleaner(self.result.image)
