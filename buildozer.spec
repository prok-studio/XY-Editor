[app]
title = XY Editor
package.name = xyeditor
package.domain = org.prokstudio
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,txt,ttf
version = 1.0

# Добавили все возможные библиотеки про запас, включая Pillow для картинок
requirements = python3,kivy==2.3.0,cython==3.0.10,android,pillow,jnius,plyer

orientation = portrait
fullscreen = 0

# Настройки стабильной сборки Android SDK/NDK
android.api = 34
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True
android.skip_update = False
android.allow_backup = True

# Включаем автоматическую склейку Java ресурсов
android.gradle_dependencies = 

[buildozer]
log_level = 2
warn_on_root = 1
