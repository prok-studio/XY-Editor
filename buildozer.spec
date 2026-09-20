[app]

title = XY Editor
package.name = xyeditor
package.domain = org.example

source.dir = .
source.include_exts = py,png,jpg,kv,atlas

# Значок приложения (лучше квадратный PNG, например 512x512)
icon.filename = %(source.dir)s/Images/XY.png

version = 1.0

# Только Kivy: numpy и matplotlib не нужны (график рисуется на canvas Kivy)
requirements = python3,kivy,android,pillow

orientation = portrait
fullscreen = 0

# Разрешения не нужны: приложение ничего не читает и не отправляет
android.permissions =

android.api = 33
android.minapi = 21
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
