# syntax=docker/dockerfile:1

###############################################################################
# ncs-base : a SMALL, version-agnostic nRF Connect SDK build image.
#
# This image contains ONLY the host tools + nrfutil. It does NOT contain any
# SDK. The actual nRF Connect SDK versions + their matching toolchains are
# installed by nrfutil into a Docker *volume* mounted at /root/ncs, so:
#
#   * the image stays small and rarely changes
#   * many SDK versions live side-by-side in the volume (like your C:\ncs)
#   * you add/remove versions with nrfutil -- no image rebuild
#   * every project + every container shares the one volume
#
# The layout produced in the volume mirrors a native Nordic install, which is
# exactly what the nRF Connect for VS Code extension auto-discovers:
#
#   /root/ncs/
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
# IMPORTANT: this must match the nRF Connect VS Code extension's own SDK install
# directory, which defaults to ~/ncs (= /root/ncs for the root user). The
# extension ignores nrfutil's configured install-dir and uses this path, so we
# align everything here: the volume is mounted at /root/ncs, the scripts install
# here, and the extension installs here too — one shared store, no copying.
ENV NCS_INSTALL_DIR=/root/ncs

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

# Point both nrfutil managers at the volume mount path, so the install-sdk.ps1
# CLI installs here and the extension's --install-dir (set via the
# toolchainManager.installDirectory setting) resolves toolchains from the same
# place. (SDK *discovery* by the extension is separate — see ncs-register-sdks.)
RUN mkdir -p ${NCS_INSTALL_DIR} \
    && nrfutil sdk-manager config install-dir set ${NCS_INSTALL_DIR} \
    && nrfutil toolchain-manager config --set install-dir=${NCS_INSTALL_DIR}

# The nRF Connect extension discovers SDKs by reading the CMake *user package
# registry* (~/.cmake/packages/Zephyr) — i.e. where `west zephyr-export` would
# register Zephyr. nrfutil's install does NOT do this, and ~/.cmake is in the
# container's throwaway layer, so this script (re)creates those entries for
# every SDK in the volume. It is run on each container start (postStartCommand).
COPY <<'EOF' /usr/local/bin/ncs-register-sdks
#!/usr/bin/env bash
set -eu
NCS_DIR="${NCS_INSTALL_DIR:-/root/ncs}"
REG="${HOME}/.cmake/packages/Zephyr"
mkdir -p "$REG"
count=0
for d in "$NCS_DIR"/v*/; do
	[ -d "$d" ] || continue
	pkg="${d}zephyr/share/zephyr-package/cmake"
	[ -d "$pkg" ] || continue
	h="$(printf '%s' "$pkg" | md5sum | cut -d' ' -f1)"
	printf '%s' "$pkg" > "${REG}/${h}"
	echo "registered $(basename "$d") -> $pkg"
	count=$((count + 1))
done
echo "ncs-register-sdks: registered ${count} SDK(s) for the nRF Connect extension"
EOF
RUN chmod +x /usr/local/bin/ncs-register-sdks

WORKDIR /workspaces
CMD ["bash"]
