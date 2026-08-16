"""
Сборка HelloDetector (программа детекции для Luckfox Pico Mini) в Google Colab.

Зачем Colab: кросс-компилятор под плату есть только под Linux x86_64.
GPU для этого шага НЕ нужен.

Использование:
  1. Новый ноутбук на https://colab.research.google.com/
  2. Вставьте ВСЁ содержимое этого файла в одну ячейку и запустите
  3. Когда Colab попросит файлы — загрузите:
       - my_model.rknn  (или yolov8.rknn)
       - labels.txt     (по одному классу в строке, например wemos / stm)
  4. В конце скачается HelloDetector_bin.zip
"""

import os
import re
import shutil
import urllib.request
from pathlib import Path

from google.colab import files

os.chdir("/content")

# ======================= 0. Загрузка модели и labels =========================
print("Выберите ДВА файла: my_model.rknn (или yolov8.rknn) и labels.txt")
uploaded = files.upload()
assert uploaded, "Файлы не загружены"

rknn_name = None
labels_name = None
for name in uploaded:
    low = name.lower()
    if low.endswith(".rknn"):
        rknn_name = name
    if low.endswith(".txt") and ("label" in low.replace(" ", "").lower()):
        labels_name = name
# запасной поиск labels*.txt
if labels_name is None:
    for name in uploaded:
        if name.lower().endswith(".txt"):
            labels_name = name
            break

assert rknn_name, f"Не найден .rknn среди: {list(uploaded)}"
assert labels_name, f"Не найден labels.txt среди: {list(uploaded)}"

MODEL_RKNN_PATH = f"/content/{rknn_name}"
LABELS_TXT_PATH = f"/content/{labels_name}"
# files.upload уже сохранил в /content/<name>
Path(MODEL_RKNN_PATH).write_bytes(uploaded[rknn_name])
Path(LABELS_TXT_PATH).write_bytes(uploaded[labels_name])
print("Модель:", MODEL_RKNN_PATH, "байт:", Path(MODEL_RKNN_PATH).stat().st_size)
print("Labels:", LABELS_TXT_PATH)
print(Path(LABELS_TXT_PATH).read_text(encoding="utf-8"))

BASE_REPO = "https://github.com/ret7020/Yolov8CustomNPU"
THIS_REPO = "https://github.com/Daniilslep/LuckFox_YOLO"

# 1. Кросс-компилятор
if not os.path.isdir("/content/luckfox-pico"):
    os.system("git clone --depth 1 https://github.com/LuckfoxTECH/luckfox-pico/")
os.environ["GCC_COMPILER"] = (
    "/content/luckfox-pico/tools/linux/toolchain/"
    "arm-rockchip830-linux-uclibcgnueabihf/bin/arm-rockchip830-linux-uclibcgnueabihf"
)
os.system(f"chmod +x {os.environ['GCC_COMPILER']}-*")

# 2. Базовый проект
if not os.path.isdir("/content/Yolov8CustomNPU"):
    os.system(f"git clone --depth 1 {BASE_REPO}")

# 3. Этот репозиторий — универсальный main.cc
if not os.path.isdir("/content/LuckFox_YOLO"):
    os.system(f"git clone --depth 1 {THIS_REPO}")
else:
    # подтянуть свежий main.cc, если репозиторий уже был
    os.system("cd /content/LuckFox_YOLO && git pull --ff-only || true")

proj = "/content/Yolov8CustomNPU/Yolov8"
assert os.path.isdir(proj), "Не нашёл /content/Yolov8CustomNPU/Yolov8"

# 4. main.cc
shutil.copy("/content/LuckFox_YOLO/cpp/HelloDetector/src/main.cc", f"{proj}/cpp/src/main.cc")

# 5. модель + labels
shutil.copy(MODEL_RKNN_PATH, f"{proj}/model/yolov8.rknn")
shutil.copy(LABELS_TXT_PATH, f"{proj}/model/labels.txt")

with open(f"{proj}/model/labels.txt", encoding="utf-8") as fd:
    num_classes = len([line for line in fd if line.strip()])
print(f"Классов в labels.txt: {num_classes}")
assert num_classes >= 1

# 6. OBJ_CLASS_NUM
postprocess_h = f"{proj}/cpp/include/postprocess.h"
content = Path(postprocess_h).read_text(encoding="utf-8")
content_new = re.sub(r"#define OBJ_CLASS_NUM \d+", f"#define OBJ_CLASS_NUM {num_classes}", content)
Path(postprocess_h).write_text(content_new, encoding="utf-8")
print("OBJ_CLASS_NUM =", num_classes, "patched" if content != content_new else "WARN: pattern not found")

# 6b. имя бинарника HelloDetector
cmakelists = f"{proj}/cpp/CMakeLists.txt"
cmake_content = Path(cmakelists).read_text(encoding="utf-8")
cmake_content = cmake_content.replace("project(HelloYolov8)", "project(HelloDetector)")
Path(cmakelists).write_text(cmake_content, encoding="utf-8")

# 7. OpenCV Mobile 4.10
base_url = (
    "https://raw.githubusercontent.com/LuckfoxTECH/"
    "luckfox_pico_rkmpi_example/kernel-5.10.160/lib/uclibc"
)
libdir = f"{proj}/cpp/lib"
opencv_files = [
    "lib/libopencv_core.a",
    "lib/libopencv_features2d.a",
    "lib/libopencv_highgui.a",
    "lib/libopencv_imgproc.a",
    "lib/libopencv_photo.a",
    "lib/libopencv_video.a",
    "lib/cmake/opencv4/OpenCVConfig-version.cmake",
    "lib/cmake/opencv4/OpenCVConfig.cmake",
    "lib/cmake/opencv4/OpenCVModules-release.cmake",
    "lib/cmake/opencv4/OpenCVModules.cmake",
]
for rel in opencv_files:
    url = f"{base_url}/{rel}"
    if rel.startswith("lib/cmake"):
        dest = os.path.join(libdir, rel[len("lib/") :])
    else:
        dest = os.path.join(libdir, os.path.basename(rel))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print("GET", os.path.basename(dest))
    urllib.request.urlretrieve(url, dest)
print("OpenCV Mobile 4.10 готов")

# 8. Сборка
os.chdir(f"{proj}/cpp")
os.system("rm -rf build && mkdir build")
os.chdir("build")
ret = os.system("cmake .. && make -j2 && make install")
if ret != 0:
    raise SystemExit("Сборка не удалась, смотрите вывод выше")

bin_path = f"{proj}/cpp/bin/HelloDetector"
assert os.path.isfile(bin_path), bin_path
os.system(f"ls -l {bin_path} {proj}/cpp/bin/model")

shutil.make_archive("/content/HelloDetector_bin", "zip", f"{proj}/cpp/bin")
print("Скачиваю HelloDetector_bin.zip ...")
files.download("/content/HelloDetector_bin.zip")
print("Готово.")
