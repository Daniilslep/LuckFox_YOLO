"""
Сборка HelloDetector (программа детекции для Luckfox Pico Mini) в Google Colab.

Зачем Colab: кросс-компилятор под плату (arm-rockchip830-linux-uclibcgnueabihf)
существует только под Linux x86_64. Если у вас Windows или macOS - Colab
(обычная бесплатная сессия без GPU, компилятору он не нужен) решает эту проблему.

Что нужно приготовить заранее:
  1. Файл вашей модели `yolov8.rknn` (получаете на шаге 05, colab/01_train_and_export.ipynb)
  2. Файл `labels.txt` со списком классов, по одному имени на строку, в том же порядке,
     что и при обучении (обычно совпадает с "names" в вашем data.yaml)

Загрузите оба файла в сессию Colab (проще всего - на панели слева, вкладка "Файлы",
кнопка "Загрузить в сессионное хранилище") и укажите пути ниже.

Использование: вставьте всё содержимое этого файла в одну ячейку Colab и запустите.
"""

import os
import shutil
import urllib.request

# ======================= НАСТРОЙКИ - поправьте под себя ======================
MODEL_RKNN_PATH = "/content/yolov8.rknn"     # путь к вашей модели после загрузки
LABELS_TXT_PATH = "/content/labels.txt"      # путь к вашему labels.txt
# ==============================================================================

BASE_REPO = "https://github.com/ret7020/Yolov8CustomNPU"
THIS_REPO = "https://github.com/Daniilslep/LuckFox_YOLO"

os.chdir("/content")

# 1. Кросс-компилятор
if not os.path.isdir("/content/luckfox-pico"):
    os.system("git clone --depth 1 https://github.com/LuckfoxTECH/luckfox-pico/")
os.environ["GCC_COMPILER"] = (
    "/content/luckfox-pico/tools/linux/toolchain/"
    "arm-rockchip830-linux-uclibcgnueabihf/bin/arm-rockchip830-linux-uclibcgnueabihf"
)
os.system(f"chmod +x {os.environ['GCC_COMPILER']}-*")

# 2. Базовый проект (структура cmake, обёртки RKNN, готовые библиотеки под плату)
if not os.path.isdir("/content/Yolov8CustomNPU"):
    os.system(f"git clone --depth 1 {BASE_REPO}")

# 3. Этот репозиторий - нужен универсальный main.cc с OLED + светодиодом
if not os.path.isdir("/content/LuckFox_YOLO"):
    os.system(f"git clone --depth 1 {THIS_REPO}")

proj = "/content/Yolov8CustomNPU/Yolov8"
assert os.path.isdir(proj), "Не нашёл /content/Yolov8CustomNPU/Yolov8 - клонирование не удалось?"

# 4. Кладём наш main.cc
shutil.copy("/content/LuckFox_YOLO/cpp/HelloDetector/src/main.cc", f"{proj}/cpp/src/main.cc")

# 5. Кладём вашу модель и labels.txt
assert os.path.isfile(MODEL_RKNN_PATH), f"Не найден файл модели: {MODEL_RKNN_PATH}"
assert os.path.isfile(LABELS_TXT_PATH), f"Не найден labels.txt: {LABELS_TXT_PATH}"
shutil.copy(MODEL_RKNN_PATH, f"{proj}/model/yolov8.rknn")
shutil.copy(LABELS_TXT_PATH, f"{proj}/model/labels.txt")

with open(LABELS_TXT_PATH) as fd:
    num_classes = len([line for line in fd if line.strip()])
print(f"Классов в labels.txt: {num_classes}")

# 6. Правим OBJ_CLASS_NUM под ваше количество классов - без этого будет
#    Segmentation Fault при запуске на плате
postprocess_h = f"{proj}/cpp/include/postprocess.h"
with open(postprocess_h) as fd:
    content = fd.read()
import re
content_new = re.sub(r"#define OBJ_CLASS_NUM \d+", f"#define OBJ_CLASS_NUM {num_classes}", content)
with open(postprocess_h, "w") as fd:
    fd.write(content_new)
print("OBJ_CLASS_NUM обновлён:", "OK" if content != content_new else "не найдено! проверьте файл вручную")

# 6b. Переименовываем итоговый бинарник в HelloDetector (в базовом проекте он
#     называется HelloYolov8 - это просто имя, на суть не влияет)
cmakelists = f"{proj}/cpp/CMakeLists.txt"
with open(cmakelists) as fd:
    cmake_content = fd.read()
cmake_content = cmake_content.replace("project(HelloYolov8)", "project(HelloDetector)")
with open(cmakelists, "w") as fd:
    fd.write(cmake_content)

# 7. Обновляем OpenCV Mobile до версии 4.10 - на некоторых свежих прошивках
#    платы старая версия (4.9, идёт в базовом проекте по умолчанию) падает
#    при открытии камеры с ошибкой в AIQ. Если у вас всё уже работает и без
#    этого шага - можете закомментировать блок ниже.
base_url = "https://raw.githubusercontent.com/LuckfoxTECH/luckfox_pico_rkmpi_example/kernel-5.10.160/lib/uclibc"
libdir = f"{proj}/cpp/lib"
opencv_files = [
    "lib/libopencv_core.a", "lib/libopencv_features2d.a", "lib/libopencv_highgui.a",
    "lib/libopencv_imgproc.a", "lib/libopencv_photo.a", "lib/libopencv_video.a",
    "lib/cmake/opencv4/OpenCVConfig-version.cmake", "lib/cmake/opencv4/OpenCVConfig.cmake",
    "lib/cmake/opencv4/OpenCVModules-release.cmake", "lib/cmake/opencv4/OpenCVModules.cmake",
]
for rel in opencv_files:
    url = f"{base_url}/{rel}"
    dest = os.path.join(libdir, rel[len("lib/"):] if rel.startswith("lib/cmake") else os.path.basename(rel))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    urllib.request.urlretrieve(url, dest)
print("OpenCV Mobile обновлён до 4.10")

# 8. Собираем
os.chdir(f"{proj}/cpp")
os.system("rm -rf build && mkdir build")
os.chdir("build")
ret = os.system("cmake .. && make -j2 && make install")
if ret != 0:
    raise SystemExit("Сборка не удалась, смотрите вывод выше")

bin_path = f"{proj}/cpp/bin/HelloDetector"
os.system(f"ls -l {bin_path} {proj}/cpp/bin/model")

print("\nГотово! Скачайте файл:", bin_path)
print("Также нужно скачать всю папку bin/ (в ней лежат lib/, model/ - без них бинарник не запустится).")

# Автоматическая упаковка bin/ в zip и скачивание (работает только в самом Colab)
try:
    from google.colab import files
    shutil.make_archive("/content/HelloDetector_bin", "zip", f"{proj}/cpp/bin")
    files.download("/content/HelloDetector_bin.zip")
except ImportError:
    pass
