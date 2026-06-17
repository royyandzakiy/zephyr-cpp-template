# syntax=docker/dockerfile:1

###############################################################################
# nRF Connect SDK (NCS) shared workspace image.
#
# The heavy parts -- the nRF SDK, Zephyr, every west module, and the matching
# Zephyr SDK toolchain -- are downloaded and baked into THIS image exactly once.
#
# Every project then reuses the same image (via .devcontainer or the helper
# scripts) and only bind-mounts its own source into /workspace/projects/<name>.
# Copying this template to a new project therefore costs ZERO extra SDK
# downloads: you keep using the one image you already built.
#
#   Build once:   docker build -t ncs-workspace:latest .
#   Rebuild SDK:  docker build --no-cache -t ncs-workspace:latest .
###############################################################################

FROM ubuntu:24.04

# Which nRF Connect SDK revision to check out. Defaults to the tip of main
# ("latest"). For reproducible builds, pin a release tag instead:
#   docker build --build-arg NCS_REV=v2.9.0 -t ncs-workspace:2.9.0 .
ARG NCS_REV=main

# Only the ARM toolchain is installed by default (nRF5340 is Cortex-M33).
# Set to "all" to cover every architecture.
ARG ZEPHYR_TOOLCHAINS=arm-zephyr-eabi

ENV DEBIAN_FRONTEND=noninteractive

# --- Host dependencies (Zephyr getting-started + flashing tools) -------------
RUN apt-get update && apt-get install -y --no-install-recommends \
      git cmake ninja-build gperf ccache dfu-util device-tree-compiler wget curl \
      python3-dev python3-pip python3-venv python3-setuptools python3-wheel \
      xz-utils file make gcc gcc-multilib g++-multilib \
      libsdl2-dev libmagic1 libusb-1.0-0 udev usbutils \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# --- west in an isolated venv (Ubuntu 24.04 is PEP-668 "externally managed") -
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip wheel west

# --- Initialise the NCS west workspace and pull all sources ------------------
# --narrow -o=--depth=1 keeps the clone shallow so the image stays as small as
# a full NCS checkout reasonably can.
WORKDIR /workspace
RUN west init -m https://github.com/nrfconnect/sdk-nrf --mr "$NCS_REV" . \
    && west update --narrow -o=--depth=1 \
    && west zephyr-export

# --- Python requirements for Zephyr + NCS ------------------------------------
RUN pip install --no-cache-dir -r zephyr/scripts/requirements.txt \
    && pip install --no-cache-dir -r nrf/scripts/requirements.txt

# --- Zephyr SDK (toolchain that matches this NCS revision) -------------------
RUN west sdk install --toolchains "$ZEPHYR_TOOLCHAINS"

# --- Workspace conveniences --------------------------------------------------
# Projects get mounted in here at runtime; one subfolder per project.
RUN mkdir -p /workspace/projects
ENV ZEPHYR_BASE=/workspace/zephyr

WORKDIR /workspace/projects
CMD ["bash"]
