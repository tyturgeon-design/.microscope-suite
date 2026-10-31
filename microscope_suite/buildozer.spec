[app]
title = Microscope Suite
package.name = microscopesuite
package.domain = org.microscopy
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
source.exclude_dirs = .github,bin,.buildozer,__pycache__
version = 1.0.0

# Add `av` to the list below if you want the PyAV video fallback (heavier build).
requirements = python3,kivy==2.3.0,numpy,opencv,pillow,pyjnius,android,androidstorage4kivy

orientation = portrait
fullscreen = 0

# Scoped-storage picker needs no permission on Android 10+; these cover Android 9 and older.
android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True
android.enable_androidx = True
# required by androidstorage4kivy (check its README if the build complains)
android.gradle_dependencies = androidx.documentfile:documentfile:1.0.1
android.window_soft_input_mode = adjustResize

[buildozer]
log_level = 2
warn_on_root = 1
