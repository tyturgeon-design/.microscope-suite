"""App-wide user settings (shared by all screens)."""
from kivy.event import EventDispatcher
from kivy.properties import StringProperty

FORMATS = ("PNG", "JPEG", "TIFF")
SIZES = {"Full": None, "24 MP": 24e6, "12 MP": 12e6, "8 MP": 8e6, "4 MP": 4e6}


class Settings(EventDispatcher):
    fmt = StringProperty("PNG")
    max_size = StringProperty("Full")   # applies to Cleaner exports / batch

    def max_pixels(self):
        return SIZES.get(self.max_size)

    def ext(self):
        return {"PNG": ".png", "JPEG": ".jpg", "TIFF": ".tif"}[self.fmt]


settings = Settings()
