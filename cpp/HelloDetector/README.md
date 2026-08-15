# HelloDetector

Здесь лежит только один файл — [`src/main.cc`](src/main.cc). Это не отдельный проект, а замена файла `Yolov8/cpp/src/main.cc` в базовом проекте [ret7020/Yolov8CustomNPU](https://github.com/ret7020/Yolov8CustomNPU), который уже содержит всё остальное: `CMakeLists.txt`, обёртки над RKNN (`yolov8.cc`, `postprocess.cc`), библиотеки OpenCV Mobile / RGA / RKNPU2 для платы.

Как это использовать — подробно описано в [docs/06-build-and-deploy.md](../../docs/06-build-and-deploy.md). Короткая версия:

```bash
git clone https://github.com/ret7020/Yolov8CustomNPU
cp cpp/HelloDetector/src/main.cc Yolov8CustomNPU/Yolov8/cpp/src/main.cc
cp model/labels.txt Yolov8CustomNPU/Yolov8/model/labels.txt      # ваши классы, по одному на строку
# поправить OBJ_CLASS_NUM в Yolov8CustomNPU/Yolov8/cpp/include/postprocess.h = число строк в labels.txt
cp your_model.rknn Yolov8CustomNPU/Yolov8/model/yolov8.rknn

cd Yolov8CustomNPU/Yolov8/cpp
mkdir build && cd build
cmake ..
make install
```

Результат — папка `bin/` с бинарником `HelloDetector`, файлом `model/labels.txt` и вашей моделью `model/yolov8.rknn`.

Всё это (клонирование, копирование, правку `OBJ_CLASS_NUM`, сборку и упаковку) делает готовый скрипт для Google Colab: [colab/02_build_hellodetector.py](../../colab/02_build_hellodetector.py).
