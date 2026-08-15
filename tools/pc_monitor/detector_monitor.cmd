@echo off
REM Запуск монитора детекций Luckfox Pico Mini на Windows.
REM Требуется: Python 3 c пакетами opencv-python и numpy (pip install opencv-python numpy)
REM и adb, доступный в PATH (или укажите путь в detector_monitor.py, переменная ADB).
cd /d "%~dp0"
python detector_monitor.py
pause
