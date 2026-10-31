"""Microscope Suite - touch UI for phone microscopy (Kivy).

Desktop test:  python main.py
Android APK:   buildozer android debug   (see README)
"""
from kivy.app import App
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import NoTransition, ScreenManager
from kivy.uix.togglebutton import ToggleButton
from kivy.utils import platform

from ui.cleaner_screen import CleanerScreen
from ui.measure_screen import MeasureScreen
from ui.settings_screen import SettingsScreen
from ui.stacker_screen import StackerScreen

if platform not in ("android", "ios"):
    Window.size = (420, 860)          # phone-shaped window for desktop testing
Window.softinput_mode = "below_target"


class MicroscopeApp(App):
    title = "Microscope Suite"

    def build(self):
        Window.clearcolor = (0.09, 0.09, 0.10, 1)
        root = BoxLayout(orientation="vertical")
        self.sm = ScreenManager(transition=NoTransition())

        self.measure = MeasureScreen(name="measure")
        self.clean = CleanerScreen(name="clean", send_to_measure=self._to_measure)
        self.stack = StackerScreen(name="stack", send_to_cleaner=self._to_clean)
        self.prefs = SettingsScreen(name="settings")
        for s in (self.stack, self.clean, self.measure, self.prefs):
            self.sm.add_widget(s)
        root.add_widget(self.sm)

        nav = BoxLayout(size_hint_y=None, height=dp(56))
        self.nav = {}
        for i, (name, text) in enumerate((("stack", "Stack"), ("clean", "Clean"),
                                          ("measure", "Measure"), ("settings", "Settings"))):
            b = ToggleButton(text=text, group="nav", allow_no_selection=False,
                             font_size=sp(15), background_normal="", background_down="",
                             state="down" if i == 0 else "normal",
                             background_color=(0.12, 0.12, 0.14, 1))
            b.bind(on_release=lambda w, n=name: self.go(n),
                   state=lambda w, st: setattr(w, "background_color",
                                               (0.16, 0.48, 0.85, 1) if st == "down"
                                               else (0.12, 0.12, 0.14, 1)))
            b.background_color = (0.16, 0.48, 0.85, 1) if i == 0 else b.background_color
            self.nav[name] = b
            nav.add_widget(b)
        root.add_widget(nav)

        Window.bind(on_keyboard=self._on_key)
        return root

    def go(self, name):
        self.sm.current = name
        self.nav[name].state = "down"

    def _to_clean(self, img):
        self.clean.set_image(img, "Stacked composite")
        self.go("clean")

    def _to_measure(self, img):
        self.measure.set_image(img, "Cleaned image")
        self.go("measure")

    def _on_key(self, window, key, *args):
        if key == 27 and self.sm.current != "stack":   # Android back -> first tab
            self.go("stack")
            return True
        return False

    def on_pause(self):
        return True   # stay alive while the system file picker is open


if __name__ == "__main__":
    MicroscopeApp().run()
