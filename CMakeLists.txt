# Freestanding Zephyr application. ZEPHYR_BASE is exported by the workspace
# image (/workspace/zephyr), so the app builds against the shared SDK.
cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(ncs_cpp_template LANGUAGES C CXX)

target_sources(app PRIVATE src/main.cpp)
