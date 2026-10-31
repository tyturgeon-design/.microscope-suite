"""Tab 4: export options and about."""
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.spinner import Spinner

from ui.state import FORMATS, SIZES, settings
from ui.widgets import ControlList, WrapLabel

VERSION = "1.0.0"


class SettingsScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        cl = ControlList()
        self.add_widget(cl)
        cl.add(WrapLabel(text="Export settings", font_size=sp(18)))
        cl.add(self._spinner("Output format", FORMATS, "fmt"))
        cl.add(self._spinner("Max export size (Clean tab)", tuple(SIZES), "max_size"))
        cl.add(WrapLabel(
            text="Choose a smaller max size if the app runs out of memory on a large photo. "
                 "Exports go to your Gallery (Pictures).", font_size=sp(12)))
        cl.add(WrapLabel(text=f"Microscope Suite v{VERSION}", font_size=sp(16)))
        cl.add(WrapLabel(
            text="Focus stacking, cleaning (chromatic aberration, colour fringes, flat-field, "
                 "tone, sharpening) and calibrated measurement for phone microscopy.\n\n"
                 "Open source (MIT). Built with Kivy, OpenCV and Pillow.\n\n"
                 "Gestures: pinch to zoom, drag to pan, double-tap to reset view.",
            font_size=sp(13)))

    def _spinner(self, label, values, prop):
        box = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        lbl = Label(text=label, font_size=sp(14), halign="left", valign="middle", size_hint_x=0.55)
        lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        sp_ = Spinner(text=getattr(settings, prop), values=values, font_size=sp(15))
        sp_.bind(text=lambda w, t: setattr(settings, prop, t))
        box.add_widget(lbl)
        box.add_widget(sp_)
        return box
