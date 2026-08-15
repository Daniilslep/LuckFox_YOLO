#!/bin/bash
# Скачивает и распаковывает OpenCV Mobile 4.10.0, собранный под Luckfox Pico.
# Запустите этот скрипт из директории tools/dataset_capture/libs перед сборкой.
#
# Важно: у проекта nihui/opencv-mobile "releases/latest" всегда указывает на
# самую новую версию OpenCV (сейчас это 5.0.0), а старые версии там больше не
# лежат. Поэтому ссылка обязательно должна указывать на конкретный релиз-тег
# (v31), в котором опубликована именно версия 4.10.0 для luckfox-pico -
# смотрите полный список версий и тегов на
# https://github.com/nihui/opencv-mobile/releases (искать по слову "luckfox").
set -e
VER=4.10.0
TAG=v31
URL="https://github.com/nihui/opencv-mobile/releases/download/${TAG}/opencv-mobile-${VER}-luckfox-pico.zip"
curl -L -o opencv-mobile.zip "$URL"
unzip -o opencv-mobile.zip
rm opencv-mobile.zip
echo "OpenCV Mobile ${VER} готов в $(pwd)/opencv-mobile-${VER}-luckfox-pico"
