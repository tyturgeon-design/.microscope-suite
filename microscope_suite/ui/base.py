"""Shared screen layout: status line, image view, toolbar, scrolling controls."""
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen

from ui.widgets import Btn, ControlList, ImageView, TBtn, WrapLabel


class TabScreen(Screen):
    SMALL, BIG = 0.42, 0.78

    def __init__(self, on_tap=None, **kw):
        super().__init__(**kw)
        box = BoxLayout(orientation="vertical", spacing=dp(4), padding=dp(4))
        self.add_widget(box)
        self.status = WrapLabel(text="", font_size=sp(12), color=(0.78, 0.78, 0.85, 1))
        self.view = ImageView(on_tap=on_tap, size_hint_y=self.SMALL)
        self.toolbar = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(4))
        self.controls = ControlList(size_hint_y=1 - self.SMALL)
        for w in (self.status, self.view, self.toolbar, self.controls):
            box.add_widget(w)

    def tool(self, text, cb, primary=False):
        b = Btn(text, cb, primary=primary, font=12)
        self.toolbar.add_widget(b)
        return b

    def toggle_tool(self, text, cb):
        b = TBtn(text, cb, font=12)
        self.toolbar.add_widget(b)
        return b

    def add_expand_tool(self):
        self.toggle_tool("Big view", self._expand)

    def _expand(self, on):
        h = self.BIG if on else self.SMALL
        self.view.size_hint_y = h
        self.controls.size_hint_y = 1 - h

    def set_status(self, text):
        self.status.text = text
