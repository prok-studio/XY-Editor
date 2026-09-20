СБОРКА .APK
===========

В папке должны лежать: main.py, logic.py, buildozer.spec и папка Images с файлом XY.png
(значок приложения).

0) (по желанию) Проверить на компьютере:
       pip install kivy
       python main.py

1) Buildozer работает на Linux (Ubuntu). На Windows - через WSL2 (Ubuntu),
   на Mac - через Docker или виртуальную машину. Можно также собрать в Google Colab.

2) Установка (Ubuntu):
       sudo apt update
       sudo apt install -y git zip unzip openjdk-17-jdk python3-pip autoconf \
            libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev \
            libtinfo5 cmake libffi-dev libssl-dev
       pip3 install --user --upgrade buildozer cython==0.29.36 virtualenv
       export PATH=$PATH:~/.local/bin

3) Сборка (первый раз долго - 20-40 минут, скачивается Android SDK/NDK):
       cd папка_с_проектом
       buildozer android debug

4) Готовый файл: bin/xyeditor-1.0-arm64-v8a_armeabi-v7a-debug.apk
   Скопируй на телефон и установи (разреши «установку из неизвестных источников»).
   Или с USB-отладкой:  buildozer android deploy run

Если сборка падает - пришли последние ~30 строк лога, разберёмся.
