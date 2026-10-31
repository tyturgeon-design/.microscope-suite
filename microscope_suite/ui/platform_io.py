"""File picking and exporting that works on Android (scoped storage) and desktop.

Android: uses androidstorage4kivy -> system picker + copy into app storage,
and saves results into the shared Pictures collection (shows up in Gallery).
Desktop: simple Kivy file chooser, saves to ~/Pictures/MicroscopeSuite.
"""
import time
from pathlib import Path

from kivy.app import App
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.utils import platform

from core.utils import save_image
from ui.state import settings
from ui.tasks import run_bg
from ui.widgets import Btn

_keep = []   # keep chooser objects alive while the system picker is open
_IMG = ["*.jpg", "*.jpeg", "*.png", "*.tif", "*.tiff", "*.bmp", "*.webp"]
_VID = ["*.mp4", "*.mov", "*.avi", "*.mkv", "*.m4v", "*.3gp", "*.webm"]


def pick(kind, callback, multiple=False):
    """kind: 'image' | 'video' | 'media'. callback(list_of_local_paths)."""
    if platform == "android":
        try:
            _android_pick(kind, callback, multiple)
            return
        except Exception as e:  # missing lib etc. -> fall back to Kivy chooser
            print("Android picker failed, using fallback:", e)
    _desktop_pick(kind, callback, multiple)


def _android_pick(kind, callback, multiple):
    from androidstorage4kivy import Chooser, SharedStorage
    mimes = {"image": ("image/*",), "video": ("video/*",),
             "media": ("image/*", "video/*")}[kind]

    def on_uris(uris):
        def copy():
            ss = SharedStorage()
            return [p for p in (ss.copy_from_shared(u) for u in (uris or [])) if p]
        run_bg(copy, lambda res, err: callback(res or []))

    chooser = Chooser(on_uris)
    _keep[:] = [chooser]
    try:
        chooser.choose_content(*mimes, multiple=multiple)
    except TypeError:
        chooser.choose_content(*mimes)


def _desktop_pick(kind, callback, multiple):
    from kivy.uix.filechooser import FileChooserListView
    pats = {"image": _IMG, "video": _VID, "media": _IMG + _VID}[kind]
    pats = pats + [p.upper() for p in pats]
    fc = FileChooserListView(path=str(Path.home()), filters=pats, multiselect=multiple)
    box = BoxLayout(orientation="vertical", spacing=dp(6))
    box.add_widget(fc)
    row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
    box.add_widget(row)
    pop = Popup(title="Choose file", content=box, size_hint=(0.95, 0.9))

    def ok():
        pop.dismiss()
        callback(list(fc.selection))
    row.add_widget(Btn("Cancel", pop.dismiss))
    row.add_widget(Btn("Open", ok, primary=True))
    pop.open()


def export_bgr(img, base="microscope"):
    """Blocking (run in a thread). Returns a human-readable result message."""
    name = f"{base}_{time.strftime('%Y%m%d_%H%M%S')}{settings.ext()}"
    if platform == "android":
        from androidstorage4kivy import SharedStorage
        from jnius import autoclass
        env = autoclass("android.os.Environment")
        d = Path(App.get_running_app().user_data_dir) / "exports"
        d.mkdir(parents=True, exist_ok=True)
        p = d / name
        save_image(img, p)
        SharedStorage().copy_to_shared(str(p), collection=env.DIRECTORY_PICTURES)
        p.unlink()
        return f"Saved {name}\nFind it in Gallery / Pictures."
    d = Path.home() / "Pictures" / "MicroscopeSuite"
    d.mkdir(parents=True, exist_ok=True)
    save_image(img, d / name)
    return f"Saved:\n{d / name}"
