"""Touch-friendly Kivy widgets: zoomable image view, slider rows, collapsible sections."""
import math

import cv2
import numpy as np
from kivy.graphics import (Color, Ellipse, Line, Rectangle, StencilPop,
                           StencilPush, StencilUnUse, StencilUse)
from kivy.graphics.texture import Texture
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider
from kivy.uix.switch import Switch
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget

ACCENT = (0.16, 0.48, 0.85, 1)
BTN = (0.27, 0.27, 0.31, 1)
HEADER = (0.2, 0.2, 0.25, 1)
MAX_TEX = 2400   # keep textures GPU-safe on phones


# ---------------------------------------------------------------- basic bits
def Btn(text, on_press=None, primary=False, font=15, **kw):
    b = Button(text=text, size_hint_y=None, height=dp(46), font_size=sp(font),
               background_normal="", background_down="",
               background_color=ACCENT if primary else BTN, **kw)
    if on_press:
        b.bind(on_release=lambda *_: on_press())
    return b


def TBtn(text, on_toggle=None, font=15, **kw):
    b = ToggleButton(text=text, size_hint_y=None, height=dp(46), font_size=sp(font),
                     background_normal="", background_down="", background_color=BTN, **kw)

    def _state(_, st):
        b.background_color = ACCENT if st == "down" else BTN
        if on_toggle:
            on_toggle(st == "down")
    b.bind(state=_state)
    return b


class WrapLabel(Label):
    """Left-aligned label that wraps and sizes its own height."""

    def __init__(self, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("font_size", sp(14))
        kw.setdefault("halign", "left")
        kw.setdefault("valign", "middle")
        super().__init__(**kw)
        self.bind(width=lambda *_: setattr(self, "text_size", (self.width, None)),
                  texture_size=lambda *_: setattr(
                      self, "height", max(dp(24), self.texture_size[1] + dp(8))))


class SliderRow(BoxLayout):
    def __init__(self, label, lo, hi, value, fmt="{:.2f}", on_change=None, step=0, **kw):
        super().__init__(orientation="vertical", size_hint_y=None, height=dp(66), **kw)
        self.label, self.fmt, self.default, self.on_change = label, fmt, value, on_change
        head = BoxLayout(size_hint_y=None, height=dp(26))
        self.lbl = Label(font_size=sp(13), halign="left", valign="middle")
        self.lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        rb = Button(text="reset", size_hint_x=None, width=dp(58), font_size=sp(12),
                    background_normal="", background_down="", background_color=BTN)
        rb.bind(on_release=lambda *_: self.set(self.default))
        head.add_widget(self.lbl)
        head.add_widget(rb)
        self.slider = Slider(min=lo, max=hi, value=value, step=step, size_hint_y=None,
                             height=dp(38), cursor_size=(dp(30), dp(30)))
        self.slider.bind(value=self._changed)
        self.add_widget(head)
        self.add_widget(self.slider)
        self._label()

    def _label(self):
        self.lbl.text = f"{self.label}: {self.fmt.format(self.slider.value)}"

    def _changed(self, *_):
        self._label()
        if self.on_change:
            self.on_change()

    @property
    def value(self):
        return self.slider.value

    def set(self, v):
        self.slider.value = min(max(v, self.slider.min), self.slider.max)

    def set_range(self, lo, hi):
        self.slider.min, self.slider.max = lo, hi


class ToggleRow(BoxLayout):
    def __init__(self, label, value=False, on_change=None, **kw):
        super().__init__(size_hint_y=None, height=dp(44), **kw)
        lbl = Label(text=label, font_size=sp(14), halign="left", valign="middle")
        lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.switch = Switch(active=value, size_hint_x=None, width=dp(90))
        self.switch.bind(active=lambda *_: on_change() if on_change else None)
        self.add_widget(lbl)
        self.add_widget(self.switch)

    @property
    def value(self):
        return self.switch.active

    def set(self, v):
        self.switch.active = bool(v)


class Collapsible(BoxLayout):
    def __init__(self, title, expanded=False, **kw):
        super().__init__(orientation="vertical", size_hint_y=None, **kw)
        self.bind(minimum_height=self.setter("height"))
        self.title = title
        self.header = Button(size_hint_y=None, height=dp(46), font_size=sp(15),
                             halign="left", background_normal="", background_down="",
                             background_color=HEADER)
        self.header.bind(size=lambda w, s: setattr(w, "text_size", (s[0] - dp(16), s[1])),
                         on_release=lambda *_: self.toggle())
        self.body = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4),
                              padding=(dp(6), dp(4)))
        self.body.bind(minimum_height=self.body.setter("height"))
        self.add_widget(self.header)
        self.expanded = False
        self.set_expanded(expanded)

    def set_expanded(self, on):
        if on and not self.expanded:
            self.add_widget(self.body)
        elif not on and self.expanded:
            self.remove_widget(self.body)
        self.expanded = on
        self.header.text = ("[-]  " if on else "[+]  ") + self.title

    def toggle(self):
        self.set_expanded(not self.expanded)

    def add(self, w):
        self.body.add_widget(w)
        return w


class ControlList(ScrollView):
    def __init__(self, **kw):
        super().__init__(do_scroll_x=False, bar_width=dp(4), **kw)
        self.box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6),
                             padding=(dp(2), dp(4)))
        self.box.bind(minimum_height=self.box.setter("height"))
        super().add_widget(self.box)

    def add(self, w):
        self.box.add_widget(w)
        return w


# ---------------------------------------------------------------- popups
def show_message(title, text):
    box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
    lbl = Label(text=text, font_size=sp(15), halign="center", valign="middle")
    lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
    box.add_widget(lbl)
    pop = Popup(title=title, content=box, size_hint=(0.9, None), height=dp(240))
    box.add_widget(Btn("OK", pop.dismiss, primary=True))
    pop.open()


def ask_text(title, callback, hint="", text="", numeric=False):
    box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
    ti = TextInput(text=text, hint_text=hint, multiline=False, font_size=sp(17),
                   input_filter="float" if numeric else None,
                   size_hint_y=None, height=dp(46))
    box.add_widget(ti)
    row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
    pop = Popup(title=title, content=box, size_hint=(0.9, None), height=dp(200))

    def ok():
        pop.dismiss()
        callback(ti.text.strip())
    row.add_widget(Btn("Cancel", pop.dismiss))
    row.add_widget(Btn("OK", ok, primary=True))
    box.add_widget(row)
    pop.open()


def choose_from(title, options, callback):
    box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
    sv = ScrollView()
    inner = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
    inner.bind(minimum_height=inner.setter("height"))
    pop = Popup(title=title, content=box, size_hint=(0.9, 0.7))
    for o in options:
        inner.add_widget(Btn(o, lambda o=o: (pop.dismiss(), callback(o))))
    sv.add_widget(inner)
    box.add_widget(sv)
    box.add_widget(Btn("Cancel", pop.dismiss))
    pop.open()


# ---------------------------------------------------------------- image view
class ImageView(Widget):
    """Fit-to-widget image with pinch-zoom, drag-pan, double-tap reset and tap callback.

    Tap coordinates are reported in *source* pixels (see set_image source_wh), so
    measurements stay accurate even when a downscaled proxy is displayed.
    """

    def __init__(self, on_tap=None, **kw):
        super().__init__(**kw)
        self.on_tap = on_tap
        self.texture = None
        self.iw = self.ih = 1
        self.k = 1.0               # texture px per source px
        self.zoom, self.pan = 1.0, [0.0, 0.0]
        self.points = []           # source px; drawn as measurement overlay
        self._touches, self._pinch = {}, None
        self.bind(pos=self.redraw, size=self.redraw)

    # --- content
    def set_image(self, bgr, source_wh=None):
        if bgr is None:
            self.texture = None
            self.redraw()
            return
        h, w = bgr.shape[:2]
        sw = source_wh[0] if source_wh else w
        if max(h, w) > MAX_TEX:
            f = MAX_TEX / max(h, w)
            bgr = cv2.resize(bgr, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
            h, w = bgr.shape[:2]
        rgb = np.ascontiguousarray(bgr[..., ::-1])
        if self.texture is None or self.texture.size != (w, h):
            fresh = self.texture is None
            self.texture = Texture.create(size=(w, h), colorfmt="rgb")
            self.texture.flip_vertical()
            if fresh:
                self.reset_view()
        self.texture.blit_buffer(rgb.tobytes(), colorfmt="rgb", bufferfmt="ubyte")
        self.iw, self.ih, self.k = w, h, w / sw
        self.redraw()

    def reset_view(self):
        self.zoom, self.pan = 1.0, [0.0, 0.0]

    # --- geometry (Kivy y axis points up; image y points down)
    def _geom(self):
        s = min(self.width / self.iw, self.height / self.ih) * self.zoom
        dw, dh = self.iw * s, self.ih * s
        cx, cy = self.center_x + self.pan[0], self.center_y + self.pan[1]
        return s, cx - dw / 2, cy - dh / 2, dw, dh

    def _to_tex(self, x, y):
        s, ox, oy, _, _ = self._geom()
        return (x - ox) / s, self.ih - (y - oy) / s

    def _from_tex(self, ix, iy):
        s, ox, oy, _, _ = self._geom()
        return ox + ix * s, oy + (self.ih - iy) * s

    def _clamp(self):
        _, _, _, dw, dh = self._geom()
        lx, ly = (dw + self.width) / 2 - dp(40), (dh + self.height) / 2 - dp(40)
        self.pan[0] = max(-lx, min(lx, self.pan[0]))
        self.pan[1] = max(-ly, min(ly, self.pan[1]))

    # --- drawing
    def redraw(self, *_):
        self.canvas.clear()
        with self.canvas:
            Color(0.07, 0.07, 0.08, 1)
            Rectangle(pos=self.pos, size=self.size)
            if self.texture is None:
                return
            StencilPush()
            Rectangle(pos=self.pos, size=self.size)
            StencilUse()
            _, ox, oy, dw, dh = self._geom()
            Color(1, 1, 1, 1)
            Rectangle(texture=self.texture, pos=(ox, oy), size=(dw, dh))
            pts = [self._from_tex(px * self.k, py * self.k) for px, py in self.points]
            if len(pts) == 2:
                Color(1, 0.92, 0.23, 1)
                Line(points=[*pts[0], *pts[1]], width=dp(1.5))
            Color(1, 0.32, 0.32, 1)
            for x, y in pts:
                Line(circle=(x, y, dp(9)), width=dp(1.5))
            StencilUnUse()
            Rectangle(pos=self.pos, size=self.size)
            StencilPop()

    # --- touch: one finger pan/tap, two fingers pinch, double-tap reset
    def on_touch_down(self, t):
        if not self.collide_point(*t.pos):
            return False
        t.grab(self)
        self._touches[t.uid] = {"pos": t.pos, "start": t.pos, "moved": False}
        if t.is_double_tap:
            self.reset_view()
            self.redraw()
            for d in self._touches.values():
                d["moved"] = True
        if len(self._touches) >= 2:
            for d in self._touches.values():
                d["moved"] = True
            self._pinch = self._pinch_state()
        return True

    def _pinch_state(self):
        a, b = [d["pos"] for d in list(self._touches.values())[:2]]
        return (math.hypot(a[0] - b[0], a[1] - b[1]), ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))

    def on_touch_move(self, t):
        if t.grab_current is not self or t.uid not in self._touches:
            return False
        d = self._touches[t.uid]
        d["pos"] = t.pos
        if len(self._touches) == 1:
            if not d["moved"] and math.hypot(t.x - d["start"][0], t.y - d["start"][1]) > dp(10):
                d["moved"] = True
            if d["moved"] and self.texture is not None:
                self.pan[0] += t.dx
                self.pan[1] += t.dy
                self._clamp()
                self.redraw()
        elif self._pinch and self._pinch[0] > 1 and self.texture is not None:
            dist, mid = self._pinch_state()
            new = min(40.0, max(1.0, self.zoom * dist / self._pinch[0]))
            f = new / self.zoom
            cx, cy = self.center_x + self.pan[0], self.center_y + self.pan[1]
            ncx = mid[0] + (cx - self._pinch[1][0]) * f
            ncy = mid[1] + (cy - self._pinch[1][1]) * f
            self.pan = [ncx - self.center_x, ncy - self.center_y]
            self.zoom = new
            self._pinch = (dist, mid)
            self._clamp()
            self.redraw()
        return True

    def on_touch_up(self, t):
        if t.grab_current is not self:
            return False
        t.ungrab(self)
        d = self._touches.pop(t.uid, None)
        self._pinch = self._pinch_state() if len(self._touches) >= 2 else None
        if d and not d["moved"] and not self._touches and self.on_tap and self.texture is not None:
            ix, iy = self._to_tex(*t.pos)
            if 0 <= ix < self.iw and 0 <= iy < self.ih:
                self.on_tap(ix / self.k, iy / self.k)
        return True


# ---------------------------------------------------------------- mini charts
class HistView(Widget):
    COLORS = ((0.3, 0.5, 1, 1), (0.3, 0.85, 0.3, 1), (1, 0.3, 0.3, 1))   # B, G, R

    def __init__(self, **kw):
        super().__init__(**kw)
        self.data = None
        self.bind(pos=self.redraw, size=self.redraw)

    def set_data(self, data):
        self.data = data
        self.redraw()

    def redraw(self, *_):
        self.canvas.clear()
        with self.canvas:
            Color(0.1, 0.1, 0.12, 1)
            Rectangle(pos=self.pos, size=self.size)
            if not self.data:
                return
            for arr, col in zip(self.data, self.COLORS):
                n = len(arr)
                pts = []
                for i, v in enumerate(arr):
                    pts += [self.x + i * self.width / (n - 1),
                            self.y + dp(2) + float(v) * (self.height - dp(4))]
                Color(*col)
                Line(points=pts, width=dp(1.2))


class PlotView(Widget):
    """Per-frame sharpness plot; highlighted points = frames used in the merge."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.values, self.flags = [], []
        self.bind(pos=self.redraw, size=self.redraw)

    def set_data(self, values, flags):
        self.values, self.flags = list(values), list(flags)
        self.redraw()

    def redraw(self, *_):
        self.canvas.clear()
        with self.canvas:
            Color(0.1, 0.1, 0.12, 1)
            Rectangle(pos=self.pos, size=self.size)
            n = len(self.values)
            if n < 2:
                return
            mx = max(self.values) or 1
            pad = dp(6)
            pts = []
            for i, v in enumerate(self.values):
                pts += [self.x + pad + (self.width - 2 * pad) * i / (n - 1),
                        self.y + pad + (self.height - 2 * pad) * v / mx]
            Color(0.3, 0.75, 0.95, 1)
            Line(points=pts, width=dp(1.2))
            Color(1, 0.72, 0.3, 1)
            r = dp(2.2)
            for i, used in enumerate(self.flags):
                if used:
                    Ellipse(pos=(pts[2 * i] - r, pts[2 * i + 1] - r), size=(2 * r, 2 * r))
