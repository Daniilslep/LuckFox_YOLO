#!/bin/bash
# Скачивает и распаковывает OpenCV Mobile 4.10.0, собранный под Luckfox Pico.
# Запустите этот скрипт из директории tools/dataset_capture/libs перед сборкой.
set -e
VER=4.10.0
URL="https://github.com/nihui/opencv-mobile/releases/download/v${VER}/opencv-mobile-${VER}-luckfox-pico.zip"
curl -L -o opencv-mobile.zip "$URL"
unzip -o opencv-mobile.zip
rm opencv-mobile.zip
echo "OpenCV Mobile ${VER} готов в $(pwd)/opencv-mobile-${VER}-luckfox-pico"
