"""
Просмотр детекций с Luckfox Pico Mini в реальном времени с компьютера, через ADB.

Показывает окно с картинкой последнего кадра камеры (out.jpg с платы), рамками
и подписями найденных объектов, плюс количество объектов и их координаты в консоли
и на экране. Никаких дополнительных проводов не нужно - всё идёт через тот же
USB/ADB, через который вы заливали программу на плату.

Запуск: см. detector_monitor.cmd (Windows) или просто
    python detector_monitor.py
Выход: клавиша Q в открывшемся окне, либо Ctrl+C в консоли.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

# ============================ НАСТРОЙКИ ============================
# Если adb есть в PATH - оставьте "adb". Если нет - укажите полный путь
# к adb.exe (например, из папки, куда распаковали ADB с wiki.luckfox.com).
ADB = shutil.which("adb") or "adb"

# Папка на плате, куда вы залили HelloDetector (см. docs/06-build-and-deploy.md)
REMOTE_DIR = "/root/detector"
BINARY_NAME = "HelloDetector"
MODEL_PATH = "model/yolov8.rknn"

REMOTE_JPG = f"{REMOTE_DIR}/out.jpg"
REMOTE_LOG = f"{REMOTE_DIR}/detector.log"
LOCAL_JPG = Path(__file__).with_name("_preview.jpg")

# Порог уверенности для отображения (полезно, если хочется скрыть слабые детекции
# без пересборки/перезапуска программы на плате)
MIN_CONF = 0.50
# =====================================================================

DET_RE = re.compile(r"cls=\d+\s+p=([\d.]+)\s+box=([\d,-]+)\s+(\S+)")
DETS_LINE_RE = re.compile(r"^dets=(\d+)\s*$")
CAM_DETS_RE = re.compile(r"\bcam=.*\bdets=(\d+)")


def adb(*args: str, timeout: float = 8.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        [ADB, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def ensure_adb() -> bool:
    r = adb("devices")
    for line in (r.stdout or "").splitlines():
        if line.strip().endswith("device"):
            return True
    print("ADB: устройство не найдено, перезапуск adb...")
    adb("kill-server")
    adb("start-server")
    r = adb("devices")
    print(r.stdout or r.stderr)
    for line in (r.stdout or "").splitlines():
        if line.strip().endswith("device"):
            return True
    return False


def ensure_detector() -> None:
    if not ensure_adb():
        print("Плата не видна в ADB. Проверьте кабель/подключение и запустите снова.")
        raise SystemExit(2)
    r = adb("shell", f"pidof {BINARY_NAME}")
    if r.stdout.strip():
        print(f"Программа уже запущена, PID={r.stdout.strip()}")
        return
    print("Программа не запущена - запускаю...")
    cmd = (
        f"killall {BINARY_NAME} rkipc 2>/dev/null; "
        f"cd {REMOTE_DIR}; "
        f"export LD_LIBRARY_PATH={REMOTE_DIR}/lib; "
        f"rm -f {REMOTE_LOG}; "
        f"nohup sh -c './{BINARY_NAME} {MODEL_PATH} 2>&1 | tee {REMOTE_LOG}' >/dev/null & "
        f"sleep 2; pidof {BINARY_NAME}"
    )
    r = adb("shell", cmd, timeout=20)
    print(r.stdout.strip() or r.stderr.strip())
    if not (r.stdout or "").strip():
        print(f"Не удалось запустить {BINARY_NAME} на плате.")
        raise SystemExit(3)


def pull_preview() -> bool:
    r = adb("pull", REMOTE_JPG, str(LOCAL_JPG))
    return r.returncode == 0 and LOCAL_JPG.exists()


def read_log_tail(n: int = 200) -> str:
    r = adb("shell", f"tail -n {n} '{REMOTE_LOG}' 2>/dev/null")
    return r.stdout or ""


def _det_from_match(m: re.Match) -> dict | None:
    p = float(m.group(1))
    if p < MIN_CONF:
        return None
    return {"p": p, "box": m.group(2), "name": m.group(3)}


def parse_latest_frame(log: str) -> list[dict]:
    """Детекции из последнего завершённого кадра (блок dets= ... cam=)."""
    lines = log.splitlines()

    last_cam = -1
    for i, line in enumerate(lines):
        if CAM_DETS_RE.search(line):
            last_cam = i
    if last_cam < 0:
        last_dets = -1
        for i, line in enumerate(lines):
            if DETS_LINE_RE.match(line.strip()):
                last_dets = i
        if last_dets < 0:
            return []
        dets: list[dict] = []
        for line in lines[last_dets + 1:]:
            s = line.strip()
            if s.startswith("cam=") or DETS_LINE_RE.match(s) or s.startswith("validCount"):
                break
            m = DET_RE.search(s)
            if m:
                d = _det_from_match(m)
                if d:
                    dets.append(d)
        return dets

    last_dets = -1
    for i in range(last_cam - 1, -1, -1):
        s = lines[i].strip()
        if DETS_LINE_RE.match(s):
            last_dets = i
            break
        if CAM_DETS_RE.search(s):
            break

    dets = []
    if last_dets >= 0:
        for line in lines[last_dets + 1: last_cam]:
            m = DET_RE.search(line.strip())
            if m:
                d = _det_from_match(m)
                if d:
                    dets.append(d)
    return dets


def format_report(dets: list[dict]) -> str:
    n = len(dets)
    lines = [f"Объектов: {n}"]
    for i, d in enumerate(dets, 1):
        lines.append(f"  #{i}  p={d['p']:.2f}  box={d['box']}  ({d['name']})")
    return "\n".join(lines)


def main() -> int:
    try:
        import cv2
        import numpy as np
    except ImportError:
        print("Нужен OpenCV: pip install opencv-python")
        return 1

    ensure_detector()
    print("\nОкно 'detector live' — Q для выхода")
    print("В окне и в консоли: число объектов + координаты каждого (x1,y1,x2,y2)\n")

    last_key = ""
    win = "detector live"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, 720, 560)

    try:
        while True:
            log = read_log_tail(200)
            dets = parse_latest_frame(log)
            report = format_report(dets)
            if report != last_key:
                print(report, flush=True)
                print("-" * 40, flush=True)
                last_key = report

            frame = None
            if pull_preview():
                frame = cv2.imread(str(LOCAL_JPG))
            if frame is None:
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(
                    frame, "waiting for out.jpg...", (30, 240),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2,
                )

            for d in dets:
                parts = d["box"].split(",")
                if len(parts) != 4:
                    continue
                try:
                    x1, y1, _x2, _y2 = (int(p) for p in parts)
                except ValueError:
                    continue
                label = f"{d['name']} {d['p']:.2f}"
                ty = max(y1 - 8, 18)
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
                cv2.rectangle(frame, (x1, ty - th - 4), (x1 + tw + 4, ty + 2), (0, 180, 0), -1)
                cv2.putText(
                    frame, label, (x1 + 2, ty),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA,
                )

            panel_h = min(36 + max(1, len(dets)) * 28, frame.shape[0] // 2)
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 0), (frame.shape[1], panel_h), (20, 20, 20), -1)
            frame = cv2.addWeighted(overlay, 0.75, frame, 0.25, 0)

            color = (0, 220, 0) if dets else (0, 0, 220)
            cv2.putText(
                frame, f"Objects: {len(dets)}", (10, 26),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2, cv2.LINE_AA,
            )
            y = 54
            for i, d in enumerate(dets, 1):
                parts = d["box"].split(",")
                if len(parts) == 4:
                    line = f"#{i} {d['name']} p={d['p']:.2f}  x1={parts[0]} y1={parts[1]} x2={parts[2]} y2={parts[3]}"
                else:
                    line = f"#{i} {d['name']} p={d['p']:.2f}  box={d['box']}"
                cv2.putText(
                    frame, line, (10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (240, 240, 240), 1, cv2.LINE_AA,
                )
                y += 28
                if y > panel_h - 4:
                    break

            cv2.imshow(win, frame)
            k = cv2.waitKey(120) & 0xFF
            if k in (ord("q"), ord("Q"), 27):
                break
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
