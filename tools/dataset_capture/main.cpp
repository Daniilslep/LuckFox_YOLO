// Маленькая программа для сбора датасета прямо с CSI-камеры Luckfox Pico.
//
// Как работает:
//   1. Спрашивает имя класса (папка с таким именем создастся рядом с программой).
//   2. Каждый раз, когда вы нажимаете Enter в консоли (adb shell), сохраняет очередной
//      кадр с камеры в файл <class_name>/<N>.jpg.
//   3. Чтобы закончить, введите "q" и нажмите Enter.
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

int main()
{
    std::string className;
    printf("Введите имя класса (латиницей, без пробелов), затем Enter: ");
    fflush(stdout);
    std::getline(std::cin, className);
    if (className.empty())
    {
        printf("Имя класса не может быть пустым\n");
        return -1;
    }

    mkdir(className.c_str(), 0777);

    cv::VideoCapture cap;
    cap.set(cv::CAP_PROP_FRAME_WIDTH, FRAME_WIDTH);
    cap.set(cv::CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT);
    if (!cap.open(CAMERA_DEV))
    {
        printf("Не удалось открыть камеру /dev/video%d. Выполните killall rkipc и попробуйте снова.\n", CAMERA_DEV);
        return -1;
    }

    // "прогрев" камеры - первые кадры часто бывают тёмными/неправильными
    cv::Mat frame;
    for (int i = 0; i < 5; i++) cap >> frame;

    printf("Готово. Наведите камеру на объект '%s' и нажимайте Enter для каждого снимка.\n", className.c_str());
    printf("Введите 'q' и Enter, когда закончите.\n");

    int index = 0;
    std::string line;
    while (true)
    {
        if (!std::getline(std::cin, line)) break;
        if (line == "q" || line == "Q") break;

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
        printf("Сохранено: %s  (всего: %d)\n", path, index);
    }

    printf("Готово, снято %d кадров в папке '%s'\n", index, className.c_str());
    cap.release();
    return 0;
}
