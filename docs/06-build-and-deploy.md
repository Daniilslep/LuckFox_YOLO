# 6. Сборка программы детекции и запуск на плате

К этому моменту у вас должны быть два файла с предыдущего шага: `my_model.rknn` (или `yolov8.rknn`) и `labels.txt`.

Программа для платы (`HelloDetector`) написана на C++ и собирается кросс-компилятором под ARM. Как и с обучением — если у вас не Linux, самый простой путь — собрать в Google Colab.

## 6.1. Сборка в Google Colab

1. Откройте новый ноутбук на https://colab.research.google.com/ (GPU для этого шага **не нужен**).
2. Откройте файл [`colab/02_build_hellodetector.py`](../colab/02_build_hellodetector.py), скопируйте всё содержимое в одну ячейку Colab и запустите.
3. Когда Colab попросит файлы — загрузите `my_model.rknn` (или `yolov8.rknn`) и `labels.txt`. Пути в скрипте править не обязательно: скрипт сам находит `.rknn` и `labels*.txt` среди загруженных файлов.
4. Скрипт сам:
   - скачает кросс-компилятор Luckfox;
   - склонирует базовый проект [ret7020/Yolov8CustomNPU](https://github.com/ret7020/Yolov8CustomNPU);
   - склонирует этот репозиторий и подставит универсальный `main.cc` с OLED и светодиодом;
   - подставит вашу модель и `labels.txt`, автоматически поправит число классов в коде;
   - обновит OpenCV Mobile до версии 4.10;
   - соберёт проект и скачает архив `HelloDetector_bin.zip`.

Если что-то пошло не так — читайте вывод ячейки (там шаги cmake/make).

## 6.2. Что внутри архива

```text
HelloDetector_bin.zip
├── HelloDetector      бинарник, который запускаем на плате
├── lib/                нужные .so библиотеки (OpenCV, RGA, RKNN runtime)
└── model/
    ├── yolov8.rknn      ваша модель
    └── labels.txt       ваши классы
```

Распакуйте архив на компьютере — например, в папку `HelloDetector`.

## 6.3. Заливаем на плату

```powershell
adb shell "killall rkipc HelloDetector 2>/dev/null; mkdir -p /root/detector"
adb push HelloDetector\. /root/detector/
adb shell chmod +x /root/detector/HelloDetector
```

(На Linux/macOS команды такие же, только вместо `\.` используйте `/.` или просто путь к папке.)

## 6.4. Запуск

```powershell
adb shell
```

Внутри плату:

```bash
killall rkipc
cd /root/detector
export LD_LIBRARY_PATH=/root/detector/lib
./HelloDetector model/yolov8.rknn
```

Если всё хорошо, увидите в консоли что-то похожое на:

```text
opening camera 11...
camera ok
init_post_process...
init_yolov8_model model/yolov8.rknn...
model ok
cam=0.150 infer=0.680 fps=1.5 dets=0
  cls=0 p=0.87 box=102,123,420,406 my_object
cam=0.140 infer=0.660 fps=1.5 dets=1
...
```

- Строка `dets=N` — сколько объектов найдено на кадре.
- Встроенный светодиод **USER** на плате загорается, когда объект найден, и гаснет, когда нет.
- Файл `out.jpg` в той же папке обновляется на каждом кадре — можно скачать и посмотреть (`adb pull /root/detector/out.jpg`), либо смотреть его в реальном времени инструментом из [08-pc-monitor-tool.md](08-pc-monitor-tool.md).
- Если подключили OLED-экран — на нём тоже появится количество найденных объектов и их координаты, см. [07-oled-display.md](07-oled-display.md).

## 6.5. Частые проблемы

| Симптом | Причина / решение |
|---|---|
| `camera open failed` | не выполнили `killall rkipc` перед запуском |
| `init_yolov8_model fail` | неверный путь к модели, либо файл `.rknn` повреждён/не докачался |
| Segmentation fault сразу при старте | не совпадает `OBJ_CLASS_NUM` в `postprocess.h` с реальным числом классов в модели (при сборке через `colab/02_build_hellodetector.py` это делается автоматически, если собираете руками — проверьте) |
| Камера падает с ошибкой в логах AIQ/ISP | несовместимость версии OpenCV Mobile с прошивкой — пересоберите через `colab/02_build_hellodetector.py`, там уже используется рабочая версия 4.10 |
| Не хватает памяти (`Can't allocate memory`) | проверьте, что включён swap — см. [03-first-boot-setup.md](03-first-boot-setup.md) |

Дальше — опционально: [07-oled-display.md](07-oled-display.md) (экран) и [08-pc-monitor-tool.md](08-pc-monitor-tool.md) (просмотр с компьютера).
