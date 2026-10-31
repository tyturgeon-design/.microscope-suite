"""Background-work helpers so heavy OpenCV calls never block the touch UI."""
import threading
import traceback

from kivy.clock import Clock


def run_bg(fn, done=None):
    """Run fn() in a thread; call done(result, error) on the UI thread."""
    def work():
        try:
            res, err = fn(), None
        except Exception as e:  # noqa: BLE001 - surfaced to the UI
            traceback.print_exc()
            res, err = None, e
        if done:
            Clock.schedule_once(lambda dt: done(res, err))
    threading.Thread(target=work, daemon=True).start()


def on_ui(fn, *args):
    """Call fn(*args) on the UI thread (safe from worker threads)."""
    Clock.schedule_once(lambda dt: fn(*args))


class LatestWorker:
    """Runs fn(*args) off-thread; if submit() is called while busy, only the
    newest request is kept. Results go to on_result(result) on the UI thread."""

    def __init__(self, fn, on_result):
        self.fn, self.on_result = fn, on_result
        self._lock = threading.Lock()
        self._pending = None
        self._running = False

    def submit(self, *args):
        with self._lock:
            self._pending = args
            if self._running:
                return
            self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            with self._lock:
                args, self._pending = self._pending, None
                if args is None:
                    self._running = False
                    return
            try:
                res = self.fn(*args)
            except Exception:  # noqa: BLE001
                traceback.print_exc()
                continue
            Clock.schedule_once(lambda dt, r=res: self.on_result(r))
