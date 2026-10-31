# Microscope Suite

Touch-first Android/desktop app (Kivy + OpenCV) for phone-on-eyepiece microscopy.

| Tab | What it does |
|---|---|
| **Stack** | Focus-stack a video recorded while turning the fine-focus knob (per-frame Laplacian variance, per-pixel sharpest-region merge, optional alignment). |
| **Clean** | Auto-detect + crop the circular vignette, lateral chromatic-aberration alignment (shift + radial scale, auto-align), colour-fringe suppressor, flat-field from a blank-slide photo, background flatten, white balance, levels, CLAHE, gamma/contrast/brightness/saturation, denoise, sharpen, histogram, presets, batch mode. |
| **Measure** | Tap two points, calibrate from a known length (or enter µm/px), read distances in µm/mm, and stamp a scale bar on the full-resolution image. |

Gestures: pinch to zoom, drag to pan, double-tap to reset the view.
Exports go to **Pictures** (Gallery) on Android, or `~/Pictures/MicroscopeSuite` on desktop.

## Run on desktop
```bash
pip install -r requirements.txt
python main.py
```

## Build the APK
```bash
pip install buildozer cython
buildozer android debug        # first build downloads the SDK/NDK and compiles OpenCV (slow)
```
Or push a tag (`git tag v1.0.0 && git push --tags`) / run the **Build APK** workflow on GitHub Actions.

## Known limitations
- **Video decoding:** the Android OpenCV build may lack an FFmpeg decoder. The app falls back to
  PyAV if `av` is in `requirements`; if neither works, trim/convert the video or stack on desktop.
- **Memory:** full-resolution processing of 12 MP+ photos needs RAM. Use *Settings → Max export size*.
- Picking a video copies it into app storage first, so large videos take a moment.
- The Android packaging (androidstorage4kivy, OpenCV recipe) was written but not build-tested yet;
  see `buildozer.spec` comments if the build complains.

## Layout
```
main.py            app shell + navigation
core/              OpenCV logic (no UI): stacking, enhance, measure, video, utils
ui/                Kivy screens, widgets, file picking / exporting
buildozer.spec     Android build config
```
MIT licensed.
