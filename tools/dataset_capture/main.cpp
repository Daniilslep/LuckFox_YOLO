// Маленькая программа для сбора датасета прямо с CSI-камеры Luckfox Pico.
// Поддерживает сразу несколько классов за один запуск (каждый - в свою папку).
//
// Как работает:
//   1. Спрашивает, сколько классов вы хотите снять (от 1 до MAX_CLASSES).
//   2. Для каждого класса спрашивает его имя (папка с таким именем создастся
//      рядом с программой) и переходит в режим съёмки.
//   3. Каждый раз, когда вы нажимаете Enter в консоли (adb shell), сохраняет очередной
//      кадр с камеры в файл <class_name>/<N>.jpg.
//   4. Введите "n" и Enter, чтобы закончить текущий класс и перейти к следующему.
//      Введите "q" и Enter, чтобы закончить всё прямо сейчас.
//
// Ограничение MAX_CLASSES не техническое (сама модель может иметь и больше классов),
// а практическое: чем больше классов - тем больше фотографий и разметки нужно,
// чтобы модель нормально обучилась, а плата - совсем маленькая (nano-модель, 0.5 TOPS
// NPU, десятки МБ ОЗУ). Для хобби-проекта 1-5 классов - разумный предел, см. docs/04-dataset.md.
//
// Собирается тем же способом, что и остальные примеры на плате (см. docs/04-dataset.md).

#include <opencv2/core/core.hpp>
#include <opencv2/highgui/highgui.hpp>
#include <opencv2/imgproc/imgproc.hpp>
#include <cstdio>
#include <cstring>
#include <string>
#include <iostream>
#include <sys/stat.h>

// Устройство камеры: узнать через `v4l2-ctl --list-devices` (см. docs/03-first-boot-setup.md)
#define CAMERA_DEV 11
#define FRAME_WIDTH 640
#define FRAME_HEIGHT 640
#define MAX_CLASSES 5

static int ask_class_count()
{
    std::string line;
    while (true)
    {
        printf("Сколько классов (объектов) хотите снять за этот сеанс? (1-%d): ", MAX_CLASSES);
        fflush(stdout);
        if (!std::getline(std::cin, line)) return 1;
        if (line.empty()) continue;
        int n = atoi(line.c_str());
        if (n >= 1 && n <= MAX_CLASSES) return n;
        printf("Введите число от 1 до %d.\n", MAX_CLASSES);
    }
}

static std::string ask_class_name(int idx, int total)
{
    std::string name;
    printf("Имя класса #%d из %d (латиницей, без пробелов): ", idx, total);
    fflush(stdout);
    std::getline(std::cin, name);
    return name;
}

// Снимает кадры для одного класса. Возвращает false, если пользователь ввёл "q"
// (полностью прервать программу), true - если ввёл "n" (перейти к следующему классу).
static bool capture_one_class(cv::VideoCapture &cap, const std::string &className)
{
    mkdir(className.c_str(), 0777);

    printf("Класс '%s': наведите камеру на объект и нажимайте Enter для каждого снимка.\n", className.c_str());
    printf("  'n' + Enter - следующий класс, 'q' + Enter - закончить всё.\n");

    int index = 0;
    std::string line;
    cv::Mat frame;
    while (true)
    {
        if (!std::getline(std::cin, line)) return false;
        if (line == "q" || line == "Q") return false;
        if (line == "n" || line == "N") break;

        cap >> frame;
        if (frame.empty())
        {
            printf("Пустой кадр, пропуск\n");
            continue;
        }

        char path[256];
        snprintf(path, sizeof(path), "%s/%d.jpg", className.c_str(), index);
        cv::imwrite(path, frame);
        index++;
        printf("Сохранено: %s  (всего для '%s': %d)\n", path, className.c_str(), index);
    }

    printf("Класс '%s' готов: снято %d кадров.\n", className.c_str(), index);
    return true;
}

int main()
{
    int classCount = ask_class_count();

    cv::VideoCapture cap;
    cap.set(cv::CAP_PROP_FRAME_WIDTH, FRAME_WIDTH);
    cap.set(cv::CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT);
    if (!cap.open(CAMERA_DEV))
    {
        printf("Не удалось открыть камеру /dev/video%d. Выполните killall rkipc и попробуйте снова.\n", CAMERA_DEV);
        return -1;
    }

    // "прогрев" камеры - первые кадры часто бывают тёмными/неправильными
    cv::Mat warmup;
    for (int i = 0; i < 5; i++) cap >> warmup;

    for (int i = 1; i <= classCount; i++)
    {
        std::string className = ask_class_name(i, classCount);
        if (className.empty())
        {
            printf("Имя класса не может быть пустым, пропускаю\n");
            continue;
        }
        if (!capture_one_class(cap, className)) break; // пользователь ввёл 'q'
    }

    printf("Готово. Датасет лежит в подпапках рядом с программой (по одной на класс).\n");
    cap.release();
    return 0;
}
