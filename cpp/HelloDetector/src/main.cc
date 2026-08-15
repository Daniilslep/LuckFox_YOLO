// HelloDetector - запуск YOLOv8 (RKNN) с камеры Luckfox Pico + вывод результата
// на встроенный светодиод USER (GPIO34) и опциональный OLED-экран (SSD1306, I2C).
//
// Основано на примере ret7020/Yolov8CustomNPU (https://github.com/ret7020/Yolov8CustomNPU).
// Имя(-ена) класса(-ов) берутся из model/labels.txt - код ничего не знает про конкретный
// объект и одинаково работает для любого количества классов, на которые вы обучите модель.
//
// Как собрать и запустить - см. docs/06-build-and-deploy.md в репозитории.

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <linux/i2c-dev.h>
#include <chrono>
#include "yolov8.h"
#include <opencv2/core/core.hpp>
#include <opencv2/highgui/highgui.hpp>
#include <opencv2/imgproc/imgproc.hpp>

#define MODEL_INPUT_SIZE 640     // должен совпадать с imgsz, на котором обучали/экспортировали модель
#define CAMERA_DEV 11            // узнать через `v4l2-ctl --list-devices` на плате
#define CONF_THRESHOLD 0.50f
#define NMS_THRESHOLD 0.30f

#define LED_GPIO 34              // встроенный светодиод USER, паять ничего не нужно

// Экран опционален. Если не подключали OLED - просто ничего не будет выводиться,
// программа продолжит работать как обычно.
#define OLED_I2C_DEV "/dev/i2c-3"
#define OLED_ADDR 0x3C
#define OLED_W 128
#define OLED_H 64
#define OLED_PAGES 8

/* ---------------------------- Светодиод USER ---------------------------- */

static void led_init()
{
    FILE *f = fopen("/sys/class/gpio/export", "w");
    if (f) { fprintf(f, "%d", LED_GPIO); fclose(f); }
    char path[64];
    snprintf(path, sizeof(path), "/sys/class/gpio/gpio%d/direction", LED_GPIO);
    f = fopen(path, "w");
    if (f) { fprintf(f, "out"); fclose(f); }
}

static void led_set(int on)
{
    char path[64];
    snprintf(path, sizeof(path), "/sys/class/gpio/gpio%d/value", LED_GPIO);
    FILE *f = fopen(path, "w");
    if (!f) return;
    fprintf(f, "%d", on ? 1 : 0);
    fclose(f);
}

/* -------------------------------- OLED (SSD1306) ------------------------------- */
// Маленький шрифт 5x7. Набор символов минимальный (цифры + несколько букв и знаков),
// его достаточно для строк "detected: N" и "no detection". Имя класса на сам экран
// не выводится (см. пояснение в docs/07-oled-display.md) - зато полностью видно
// в консоли платы (printf) и на кадре out.jpg (наложено через cv::putText).
// Если хочется вывести имя класса и на OLED - нужно дополнить таблицу FONT5x7 и
// font_index() нужными буквами по тому же принципу.

static int g_oled_fd = -1;

static const unsigned char FONT5x7[][5] = {
    {0x00,0x00,0x00,0x00,0x00}, /* space  0 */
    {0x3E,0x51,0x49,0x45,0x3E}, /* 0      1 */
    {0x00,0x42,0x7F,0x40,0x00}, /* 1      2 */
    {0x42,0x61,0x51,0x49,0x46}, /* 2      3 */
    {0x21,0x41,0x45,0x4B,0x31}, /* 3      4 */
    {0x18,0x14,0x12,0x7F,0x10}, /* 4      5 */
    {0x27,0x45,0x45,0x45,0x39}, /* 5      6 */
    {0x3C,0x4A,0x49,0x49,0x30}, /* 6      7 */
    {0x01,0x71,0x09,0x05,0x03}, /* 7      8 */
    {0x36,0x49,0x49,0x49,0x36}, /* 8      9 */
    {0x06,0x49,0x49,0x29,0x1E}, /* 9      10 */
    {0x14,0x7F,0x14,0x7F,0x14}, /* #      11 */
    {0x00,0x50,0x30,0x00,0x00}, /* ,      12 */
    {0x08,0x08,0x08,0x08,0x08}, /* -      13 */
    {0x00,0x36,0x36,0x00,0x00}, /* :      14 */
    {0x38,0x44,0x44,0x44,0x38}, /* o      15 */
    {0x7C,0x08,0x04,0x04,0x78}, /* n      16 */
    {0x38,0x44,0x44,0x48,0x7F}, /* d      17 */
    {0x38,0x54,0x54,0x54,0x18}, /* e      18 */
    {0x04,0x3F,0x44,0x40,0x20}, /* t      19 */
    {0x38,0x44,0x44,0x44,0x20}, /* c      20 */
    {0x00,0x44,0x7D,0x40,0x00}, /* i      21 */
    {0x00,0x60,0x60,0x00,0x00}, /* .      22 */
};

static int font_index(char ch)
{
    if (ch == ' ') return 0;
    if (ch >= '0' && ch <= '9') return 1 + (ch - '0');
    if (ch == '#') return 11;
    if (ch == ',') return 12;
    if (ch == '-') return 13;
    if (ch == ':') return 14;
    if (ch == 'o') return 15;
    if (ch == 'n') return 16;
    if (ch == 'd') return 17;
    if (ch == 'e') return 18;
    if (ch == 't') return 19;
    if (ch == 'c') return 20;
    if (ch == 'i') return 21;
    if (ch == '.') return 22;
    return 0;
}

static void oled_cmd(int fd, unsigned char c)
{
    unsigned char buf[2] = {0x00, c};
    write(fd, buf, 2);
}

static int oled_init()
{
    g_oled_fd = open(OLED_I2C_DEV, O_RDWR);
    if (g_oled_fd < 0) {
        printf("OLED не найден на %s (это нормально, если экран не подключён)\n", OLED_I2C_DEV);
        return -1;
    }
    if (ioctl(g_oled_fd, I2C_SLAVE, OLED_ADDR) < 0) {
        perror("oled ioctl");
        close(g_oled_fd);
        g_oled_fd = -1;
        return -1;
    }
    const unsigned char init[] = {
        0xAE, 0xD5, 0x80, 0xA8, OLED_H - 1, 0xD3, 0x00, 0x40,
        0x8D, 0x14, 0x20, 0x00, 0xA1, 0xC8, 0xDA, 0x12,
        0x81, 0xCF, 0xD9, 0xF1, 0xDB, 0x40, 0xA4, 0xA6, 0xAF
    };
    for (unsigned i = 0; i < sizeof(init); i++) oled_cmd(g_oled_fd, init[i]);
    printf("OLED инициализирован (адрес 0x%02X)\n", OLED_ADDR);
    return 0;
}

static void oled_put(unsigned char *fb, int x, int page, const char *text)
{
    while (*text && x < OLED_W - 6 && page < OLED_PAGES) {
        const unsigned char *cols = FONT5x7[font_index(*text++)];
        int base = page * OLED_W + x;
        for (int i = 0; i < 5; i++) fb[base + i] = cols[i];
        fb[base + 5] = 0;
        x += 6;
    }
}

static void oled_show_dets(object_detect_result_list *od)
{
    if (g_oled_fd < 0) return;
    unsigned char fb[OLED_W * OLED_PAGES];
    memset(fb, 0, sizeof(fb));

    char line[32];
    snprintf(line, sizeof(line), "detected: %d", od->count);
    oled_put(fb, 0, 0, line);

    if (od->count <= 0) {
        oled_put(fb, 0, 3, "no detection");
    } else {
        int page = 2;
        for (int i = 0; i < od->count && page < OLED_PAGES; i++, page++) {
            object_detect_result *d = &od->results[i];
            snprintf(line, sizeof(line), "#%d %d,%d-%d,%d",
                     i + 1, d->box.left, d->box.top, d->box.right, d->box.bottom);
            oled_put(fb, 0, page, line);
        }
    }

    oled_cmd(g_oled_fd, 0x21); oled_cmd(g_oled_fd, 0); oled_cmd(g_oled_fd, OLED_W - 1);
    oled_cmd(g_oled_fd, 0x22); oled_cmd(g_oled_fd, 0); oled_cmd(g_oled_fd, OLED_PAGES - 1);
    for (int i = 0; i < (int)sizeof(fb); i += 16) {
        unsigned char pkt[17];
        pkt[0] = 0x40;
        int n = (sizeof(fb) - i >= 16) ? 16 : (int)sizeof(fb) - i;
        memcpy(pkt + 1, fb + i, n);
        write(g_oled_fd, pkt, n + 1);
    }
}

/* -------------------------------- Детекция -------------------------------- */

static void draw_and_print(cv::Mat &frame, object_detect_result_list &od_results)
{
    for (int i = 0; i < od_results.count; i++)
    {
        object_detect_result *det_result = &(od_results.results[i]);
        int x1 = det_result->box.left;
        int y1 = det_result->box.top;
        int x2 = det_result->box.right;
        int y2 = det_result->box.bottom;
        const char *name = coco_cls_to_name(det_result->cls_id); // читается из model/labels.txt
        printf("  cls=%d p=%.2f box=%d,%d,%d,%d %s\n",
               det_result->cls_id, det_result->prop, x1, y1, x2, y2, name);
        cv::rectangle(frame, cv::Rect(x1, y1, x2 - x1, y2 - y1), cv::Scalar(0, 255, 0), 2);
        char label[64];
        snprintf(label, sizeof(label), "%s %.2f", name, det_result->prop);
        int ty = y1 > 18 ? y1 - 6 : y1 + 16;
        cv::putText(frame, label, cv::Point(x1, ty),
                    cv::FONT_HERSHEY_SIMPLEX, 0.55, cv::Scalar(0, 255, 0), 2);
    }
}

static int run_on_frame(rknn_app_context_t *ctx, cv::Mat &bgr_frame, cv::Mat &input640,
                        object_detect_result_list *od_out)
{
    cv::Mat rgb;
    cv::cvtColor(bgr_frame, rgb, cv::COLOR_BGR2RGB);
    cv::resize(rgb, input640, cv::Size(MODEL_INPUT_SIZE, MODEL_INPUT_SIZE), 0, 0, cv::INTER_LINEAR);
    rknn_run(ctx->rknn_ctx, nullptr);
    post_process(ctx, ctx->output_mems, CONF_THRESHOLD, NMS_THRESHOLD, od_out);
    draw_and_print(bgr_frame, *od_out);
    return od_out->count;
}

int main(int argc, char **argv)
{
    if (argc != 2 && argc != 3)
    {
        printf("%s <model_path> [image.jpg]\n", argv[0]);
        return -1;
    }

    const char *model_path = argv[1];
    const char *image_path = (argc == 3) ? argv[2] : nullptr;

    int ret;
    rknn_app_context_t rknn_app_ctx;
    memset(&rknn_app_ctx, 0, sizeof(rknn_app_context_t));

    led_init();
    led_set(0);
    oled_init();

    cv::VideoCapture cap;
    cv::Mat camFrame;

    if (!image_path)
    {
        printf("opening camera %d...\n", CAMERA_DEV);
        if (!cap.open(CAMERA_DEV))
        {
            printf("camera open failed - выполните killall rkipc и попробуйте снова\n");
            return -1;
        }
        printf("camera ok\n");
        cap >> camFrame;
        if (camFrame.empty())
        {
            printf("empty first frame\n");
            return -1;
        }
        printf("first frame %dx%d\n", camFrame.cols, camFrame.rows);
    }

    printf("init_post_process...\n");
    init_post_process();

    printf("init_yolov8_model %s...\n", model_path);
    ret = init_yolov8_model(model_path, &rknn_app_ctx);
    if (ret != 0)
    {
        printf("init_yolov8_model fail! ret=%d model_path=%s\n", ret, model_path);
        return -1;
    }
    printf("model ok\n");

    cv::Mat bgr640(MODEL_INPUT_SIZE, MODEL_INPUT_SIZE, CV_8UC3, rknn_app_ctx.input_mems[0]->virt_addr);
    object_detect_result_list od_results;

    if (image_path)
    {
        camFrame = cv::imread(image_path, 1);
        if (camFrame.empty())
        {
            printf("imread failed: %s\n", image_path);
            return -1;
        }
        printf("image %s %dx%d\n", image_path, camFrame.cols, camFrame.rows);
        run_on_frame(&rknn_app_ctx, camFrame, bgr640, &od_results);
        oled_show_dets(&od_results);
        led_set(od_results.count > 0);
        cv::imwrite("out.jpg", camFrame);
        printf("wrote out.jpg\n");
        return 0;
    }

    while (1)
    {
        std::chrono::steady_clock::time_point begin = std::chrono::steady_clock::now();
        cap >> camFrame;
        if (camFrame.empty())
        {
            printf("empty frame\n");
            continue;
        }
        std::chrono::steady_clock::time_point end = std::chrono::steady_clock::now();
        double cam_lat = std::chrono::duration<double>(end - begin).count();

        begin = std::chrono::steady_clock::now();
        int ndet = run_on_frame(&rknn_app_ctx, camFrame, bgr640, &od_results);
        end = std::chrono::steady_clock::now();
        double infer_lat = std::chrono::duration<double>(end - begin).count();

        printf("cam=%.3f infer=%.3f fps=%.1f dets=%d\n",
               cam_lat, infer_lat, (infer_lat > 0 ? 1.0 / infer_lat : 0.0), ndet);

        oled_show_dets(&od_results);
        led_set(ndet > 0);
        cv::imwrite("out.jpg", camFrame);
    }

    return 0;
}
