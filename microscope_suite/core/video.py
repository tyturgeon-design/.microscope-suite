"""Video reading with a fallback.

Android builds of OpenCV sometimes ship without an FFmpeg decoder, so we try
OpenCV first and fall back to PyAV (package `av`) if it is installed.
"""
import cv2


class CvVideo:
    backend = "opencv"

    def __init__(self, path):
        self.path = str(path)
        self.cap = cv2.VideoCapture(self.path)
        if not self.cap.isOpened():
            raise IOError("OpenCV could not open the video")
        self.count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 0.0
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        ok, _ = self.cap.read()
        if not ok:
            self.cap.release()
            raise IOError("OpenCV opened the file but could not decode frames")

    def read_frame(self, idx=0):
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, frame = self.cap.read()
        return frame if ok else None

    def frames(self, step=1):
        """Yield (index, BGR frame) for every `step`-th frame."""
        cap = cv2.VideoCapture(self.path)
        i = 0
        try:
            while True:
                if i % step:
                    if not cap.grab():
                        break
                else:
                    ok, frame = cap.read()
                    if not ok:
                        break
                    yield i, frame
                i += 1
        finally:
            cap.release()

    def close(self):
        self.cap.release()


class AvVideo:
    backend = "pyav"

    def __init__(self, path):
        import av  # optional dependency
        self.path = str(path)
        with av.open(self.path) as c:
            s = c.streams.video[0]
            self.fps = float(s.average_rate or 0)
            self.width, self.height = s.codec_context.width, s.codec_context.height
            n = s.frames or 0
            if not n and s.duration and self.fps:
                n = int(float(s.duration * s.time_base) * self.fps)
            self.count = n

    def frames(self, step=1):
        import av
        with av.open(self.path) as c:
            for i, f in enumerate(c.decode(video=0)):
                if i % step == 0:
                    yield i, f.to_ndarray(format="bgr24")

    def read_frame(self, idx=0):
        for i, f in self.frames(1):
            if i == int(idx):
                return f
        return None

    def close(self):
        pass


def open_video(path):
    errors = []
    for cls in (CvVideo, AvVideo):
        try:
            return cls(path)
        except Exception as e:
            errors.append(f"{cls.__name__}: {e}")
    raise IOError("Could not open video.\n" + "\n".join(errors))
