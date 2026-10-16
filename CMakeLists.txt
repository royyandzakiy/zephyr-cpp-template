# Freestanding app: builds against whichever Zephyr or NCS tree ZEPHYR_BASE (or the
# CMake package registry) points at, rather than living inside an SDK workspace.
cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(zephyr_cpp_template LANGUAGES C CXX)

target_sources(app PRIVATE src/main.cpp)
