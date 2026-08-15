cmake_minimum_required(VERSION 3.5)

project(dataset_capture)

set(CMAKE_CXX_STANDARD 11)

SET(CMAKE_C_COMPILER "$ENV{GCC_COMPILER}-gcc")
SET(CMAKE_CXX_COMPILER "$ENV{GCC_COMPILER}-g++")

set(CMAKE_SYSTEM_PROCESSOR arm)

# Путь к распакованной библиотеке opencv-mobile-4.10.0-luckfox-pico
# (скачивается скриптом download.sh, см. docs/04-dataset.md)
set(OpenCV_DIR "${CMAKE_CURRENT_SOURCE_DIR}/libs/opencv-mobile-4.10.0-luckfox-pico/lib/cmake/opencv4")

find_package(OpenCV REQUIRED)
include_directories(${OpenCV_INCLUDE_DIRS})

add_executable(dataset_capture main.cpp)
target_link_libraries(dataset_capture ${OpenCV_LIBS})
