"""
Просмотр детекций с Luckfox Pico Mini в реальном времени с компьютера, через ADB.

Показывает окно с картинкой последнего кадра камеры (out.jpg с платы), рамками
и подписями найденных объектов, плюс количество объектов и их координаты в консоли
и на экране.

Запуск: detector_monitor.cmd (Windows) или python detector_monitor.py
Выход: Q в окне или Ctrl+C.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ============================ НАСТРОЙКИ ============================
def _find_adb() -> str:
    env = os.environ.get("ADB")
    if env and Path(env).exists():
        return env
    which = shutil.which("adb")
    if which:
        return which
    candidates = [
        r"C:\Program Files\e2eSoft\iVCam\adb\adb.exe",
        r"C:\Android\platform-tools\adb.exe",
        r"C:\platform-tools\adb.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return "adb"


ADB = _find_adb()

REMOTE_DIR = "/root/detector"
BINARY_NAME = "HelloDetector"
MODEL_PATH = "model/yolov8.rknn"

REMOTE_JPG = "/tmp/out.jpg"  # HelloDetector пишет кадр сюда (tmpfs); fallback ниже
REMOTE_JPG_FALLBACKS = [REMOTE_JPG, f"{REMOTE_DIR}/out.jpg"]
# Лог пишем сюда при автозапуске; также читаем /tmp/detector.log на случай ручного старта
REMOTE_LOG = f"{REMOTE_DIR}/detector.log"
REMOTE_LOG_FALLBACKS = [REMOTE_LOG, "/tmp/detector.log"]
LOCAL_JPG = Path(__file__).with_name("_preview.jpg")

MIN_CONF = 0.50
# =====================================================================

DET_RE = re.compile(r"cls=\d+\s+p=([\d.]+)\s+box=([\d,-]+)\s+(\S+)")
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
    print(f"ADB = {ADB}")
    r = adb("devices")
    for line in (r.stdout or "").splitlines():
        if "\tdevice" in line or line.strip().endswith("\tdevice"):
            return True
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            return True
    print("ADB: устройство не найдено, перезапуск adb...")
    adb("kill-server")
    adb("start-server")
    r = adb("devices")
    print(r.stdout or r.stderr)
    for line in (r.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            return True
    return False


def _detector_running() -> bool:
    r = adb("shell", f"pidof {BINARY_NAME} 2>/dev/null")
    if (r.stdout or "").strip():
        return True
    r = adb("shell", f"ps | grep './{BINARY_NAME}' | grep -v grep")
    return bool((r.stdout or "").strip())


def ensure_detector(*, force_restart: bool = False) -> None:
    if not ensure_adb():
        print("Плата не видна в ADB. Проверьте кабель/подключение и запустите снова.")
        raise SystemExit(2)
    if _detector_running() and not force_restart:
        print(f"Программа уже запущена ({BINARY_NAME})")
        return
    if force_restart:
        print("Перезапускаю детектор на плате...")
        adb("shell", f"killall -9 {BINARY_NAME} rkipc 2>/dev/null", timeout=10)
    else:
        print("Программа не запущена — запускаю...")
    # out.jpg через symlink на tmpfs — старый бинарник не долбит Flash каждый кадр
    cmd = (
        f"killall -9 {BINARY_NAME} rkipc 2>/dev/null; sleep 1; "
        f"cd {REMOTE_DIR} && export LD_LIBRARY_PATH={REMOTE_DIR}/lib && "
        f"rm -f out.jpg && touch /tmp/out.jpg && ln -sf /tmp/out.jpg out.jpg && "
        f"rm -f {REMOTE_LOG} && "
        f"./{BINARY_NAME} {MODEL_PATH} > {REMOTE_LOG} 2>&1 & "
        f"sleep 4; "
        f"pidof {BINARY_NAME} 2>/dev/null || ps | grep './{BINARY_NAME}' | grep -v grep"
    )
    r = adb("shell", cmd, timeout=25)
    print((r.stdout or r.stderr or "").strip())
    if not _detector_running():
        print(f"Не удалось запустить {BINARY_NAME} на плате.")
        raise SystemExit(3)


def pull_preview() -> bool:
    # Копируем на плате, чтобы не читать JPEG в момент записи (это роняло HelloDetector)
    adb("shell", "cp -f /tmp/out.jpg /tmp/out_pull.jpg 2>/dev/null || cp -f /root/detector/out.jpg /tmp/out_pull.jpg 2>/dev/null")
    r = adb("pull", "/tmp/out_pull.jpg", str(LOCAL_JPG))
    if r.returncode == 0 and LOCAL_JPG.exists() and LOCAL_JPG.stat().st_size > 1000:
        return True
    for remote in REMOTE_JPG_FALLBACKS:
        r = adb("pull", remote, str(LOCAL_JPG))
        if r.returncode == 0 and LOCAL_JPG.exists() and LOCAL_JPG.stat().st_size > 1000:
            return True
    return False


def read_log_tail(n: int = 250) -> str:
    for path in REMOTE_LOG_FALLBACKS:
        r = adb("shell", f"tail -n {n} '{path}' 2>/dev/null")
        text = r.stdout or ""
        if text.strip():
            return text
    return ""


def _det_from_match(m: re.Match) -> dict | None:
    p = float(m.group(1))
    if p < MIN_CONF:
        return None
    return {"p": p, "box": m.group(2), "name": m.group(3)}


def parse_latest_frame(log: str) -> list[dict]:
    """Детекции из последнего кадра.

    Формат HelloDetector:
        cls=0 p=0.87 box=x1,y1,x2,y2 name
        ...
        cam=0.01 infer=0.12 fps=8.3 dets=1
    """
    lines = log.splitlines()
    last_cam = -1
    for i, line in enumerate(lines):
        if CAM_DETS_RE.search(line):
            last_cam = i
    if last_cam < 0:
        return []

    # границы блока: после предыдущего cam= ... до текущего cam=
    prev_cam = -1
    for i in range(last_cam - 1, -1, -1):
        if CAM_DETS_RE.search(lines[i]):
            prev_cam = i
            break

    dets: list[dict] = []
    for line in lines[prev_cam + 1 : last_cam]:
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
    last_jpg_sig = ""
    stall_ticks = 0
    win = "detector live"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, 720, 560)

    try:
        while True:
            if not _detector_running():
                print("Детектор на плате умер — перезапуск...", flush=True)
                ensure_detector(force_restart=True)
                stall_ticks = 0
                last_jpg_sig = ""

            log = read_log_tail(250)
            dets = parse_latest_frame(log)
            report = format_report(dets)
            if report != last_key:
                print(report, flush=True)
                print("-" * 40, flush=True)
                last_key = report

            frame = None
            if pull_preview():
                # сигнатура кадра: размер + первые байты — чтобы заметить «залипание»
                try:
                    raw = LOCAL_JPG.read_bytes()
                    sig = f"{len(raw)}:{raw[100:120]!r}"
                except OSError:
                    sig = ""
                if sig and sig == last_jpg_sig:
                    stall_ticks += 1
                elif sig:
                    stall_ticks = 0
                    last_jpg_sig = sig
                if stall_ticks >= 40:  # ~12 сек при waitKey(300)
                    print("out.jpg не меняется — перезапуск детектора...", flush=True)
                    ensure_detector(force_restart=True)
                    stall_ticks = 0
                    last_jpg_sig = ""
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
                    x1, y1, x2, y2 = (int(p) for p in parts)
                except ValueError:
                    continue
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
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
                    line = (
                        f"#{i} {d['name']} p={d['p']:.2f}  "
                        f"x1={parts[0]} y1={parts[1]} x2={parts[2]} y2={parts[3]}"
                    )
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
            k = cv2.waitKey(300) & 0xFF
            if k in (ord("q"), ord("Q"), 27):
                break
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
