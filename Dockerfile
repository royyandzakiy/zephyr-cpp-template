# syntax=docker/dockerfile:1

###############################################################################
# ncs-base : a SMALL, version-agnostic nRF Connect SDK build image.
#
# This image contains ONLY the host tools + nrfutil. It does NOT contain any
# SDK. The actual nRF Connect SDK versions + their matching toolchains are
# installed by nrfutil into a Docker *volume* mounted at /opt/nordic/ncs, so:
#
#   * the image stays small and rarely changes
#   * many SDK versions live side-by-side in the volume (like your C:\ncs)
#   * you add/remove versions with nrfutil -- no image rebuild
#   * every project + every container shares the one volume
#
# The layout produced in the volume mirrors a native Nordic install, which is
# exactly what the nRF Connect for VS Code extension auto-discovers:
#
#   /opt/nordic/ncs/
#   ├── toolchains/<bundle>/      (one toolchain per version)
#   ├── v3.3.0/                   (full west workspace)
#   └── v3.2.x/ ...
#
#   Build once:   docker build -t ncs-base:latest .
###############################################################################

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Where nrfutil installs SDKs + toolchains. This path is the Docker volume
# mount point; the extension is pointed here too.
ENV NCS_INSTALL_DIR=/opt/nordic/ncs

# --- Minimal host dependencies ----------------------------------------------
# nrfutil's toolchain bundles ship their own cmake/ninja/python/west, so we
# only need a lean host layer (git for west, libusb for tooling, certs, etc.).
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl wget git \
      python3 python3-venv \
      file xz-utils libusb-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# --- nrfutil + the commands the extension uses ------------------------------
RUN curl -fsSL \
      https://files.nordicsemi.com/artifactory/swtools/external/nrfutil/executables/x86_64-unknown-linux-gnu/nrfutil \
      -o /usr/local/bin/nrfutil \
    && chmod +x /usr/local/bin/nrfutil \
    && nrfutil install toolchain-manager \
    && nrfutil install sdk-manager || true

# Point both nrfutil managers at the volume mount path. The VS Code extension
# auto-discovers installed SDKs from sdk-manager's configured install dir.
RUN mkdir -p ${NCS_INSTALL_DIR} \
    && nrfutil sdk-manager config install-dir set ${NCS_INSTALL_DIR} \
    && nrfutil toolchain-manager config --set install-dir=${NCS_INSTALL_DIR}

WORKDIR /workspaces
CMD ["bash"]
