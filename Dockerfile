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
      ca-certificates curl wget git openssh-client \
      python3 python3-venv \
      file xz-utils libusb-1.0-0 \
      usbutils \
    && rm -rf /var/lib/apt/lists/*

# --- nrfutil + the commands the extension uses ------------------------------
RUN curl -fsSL \
      https://files.nordicsemi.com/artifactory/swtools/external/nrfutil/executables/x86_64-unknown-linux-gnu/nrfutil \
      -o /usr/local/bin/nrfutil \
    && chmod +x /usr/local/bin/nrfutil \
    && nrfutil install toolchain-manager \
    && nrfutil install sdk-manager \
    && nrfutil install device || true

# --- SEGGER J-Link software --------------------------------------------------
# `nrfutil device` needs SEGGER's libjlinkarm to program/debug over a J-Link;
# without it you get "JLinkARM DLL not found" and flashing fails with
# "operation not available / Unable to find a board".
#
# We use the headless .tgz (the .deb hard-depends on Qt4, absent on Ubuntu 24.04).
# CARE: the tarball ships BOTH 64-bit and 32-bit libjlinkarm with the SAME soname
# (libjlinkarm.so.9). Running `ldconfig` over its dir picks the 32-bit one and
# breaks loading on a 64-bit host. So we instead force the in-dir symlink to the
# 64-bit lib and register *only* that in an isolated dir.
RUN curl -fsSL -X POST \
      -d "accept_license_agreement=accepted" -d "submit=Download software" \
      https://www.segger.com/downloads/jlink/JLink_Linux_x86_64.tgz -o /tmp/jlink.tgz \
    && mkdir -p /opt/SEGGER \
    && tar -xzf /tmp/jlink.tgz -C /opt/SEGGER \
    && ln -sfn /opt/SEGGER/JLink_Linux_* /opt/SEGGER/JLink \
    && SO64="$(find -L /opt/SEGGER/JLink/ -maxdepth 1 -name 'libjlinkarm.so.*' ! -name '*_x86*' -type f | sort -V | tail -1)" \
    && ln -sf "$(basename "$SO64")" /opt/SEGGER/JLink/libjlinkarm.so.9 \
    && ln -sf libjlinkarm.so.9 /opt/SEGGER/JLink/libjlinkarm.so \
    && mkdir -p /usr/local/lib/jlink \
    && ln -sf "$SO64" /usr/local/lib/jlink/libjlinkarm.so.9 \
    && ln -sf libjlinkarm.so.9 /usr/local/lib/jlink/libjlinkarm.so \
    && echo /usr/local/lib/jlink > /etc/ld.so.conf.d/jlink.conf \
    && ldconfig \
    && rm -f /tmp/jlink.tgz
ENV PATH="/opt/SEGGER/JLink:${PATH}"

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
# Register EVERY west workspace in the install dir (official NCS *and* custom
# SDKs with any folder name) in the CMake user package registry, so the nRF
# Connect extension discovers them. A dir qualifies if it contains
# zephyr/share/zephyr-package/cmake (i.e. it's a real Zephyr/NCS workspace).
set -eu
NCS_DIR="${NCS_INSTALL_DIR:-/root/ncs}"
REG="${HOME}/.cmake/packages/Zephyr"
mkdir -p "$REG"
count=0
for d in "$NCS_DIR"/*/; do
	name="$(basename "$d")"
	# skip nrfutil's support folders, not SDKs
	case "$name" in toolchains|downloads|tmp) continue ;; esac
	pkg="${d}zephyr/share/zephyr-package/cmake"
	[ -d "$pkg" ] || continue
	h="$(printf '%s' "$pkg" | md5sum | cut -d' ' -f1)"
	printf '%s' "$pkg" > "${REG}/${h}"
	echo "registered ${name} -> ${pkg}"
	count=$((count + 1))
done
echo "ncs-register-sdks: registered ${count} SDK(s) for the nRF Connect extension"
EOF
RUN chmod +x /usr/local/bin/ncs-register-sdks

# ncs-ssh-key: ensure an SSH key exists and print its PUBLIC part. REUSES the
# existing key (the ~/.ssh dir is persisted in the ncs-ssh volume), so once you
# add it to your Git host it keeps working across rebuilds. Pass --new to force
# a fresh key. Non-interactive — safe for postCreateCommand.
COPY <<'EOF' /usr/local/bin/ncs-ssh-key
#!/usr/bin/env bash
set -eu
KEY="${HOME}/.ssh/id_ed25519"
mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"
[ "${1:-}" = "--new" ] && rm -f "$KEY" "${KEY}.pub"
if [ ! -f "$KEY" ]; then
	ssh-keygen -t ed25519 -C "ncs-devcontainer" -f "$KEY" -N "" -q
fi
chmod 600 "$KEY" 2>/dev/null || true
chmod 644 "${KEY}.pub" 2>/dev/null || true
echo "=================================================================="
echo "  SSH PUBLIC KEY — add it to your Git host to clone private repos:"
echo "------------------------------------------------------------------"
cat "${KEY}.pub"
echo "=================================================================="
EOF
RUN chmod +x /usr/local/bin/ncs-ssh-key

# ncs-ssh-setup <host>: guided authorization. Ensures a key, opens the host's
# SSH-keys page in your browser ($BROWSER is wired to the host by VS Code), then
# loops verifying `ssh -T` until the key is accepted. Run it in the terminal.
#   ncs-ssh-setup bitbucket.org   (also: github.com, gitlab.com)
COPY <<'EOF' /usr/local/bin/ncs-ssh-setup
#!/usr/bin/env bash
set -eu
HOST="${1:-bitbucket.org}"
ncs-ssh-key
ssh-keyscan -t ed25519,rsa "$HOST" >> "${HOME}/.ssh/known_hosts" 2>/dev/null || true
case "$HOST" in
	bitbucket.org) URL="https://bitbucket.org/account/settings/ssh-keys/" ;;
	github.com)    URL="https://github.com/settings/ssh/new" ;;
	gitlab.com)    URL="https://gitlab.com/-/user_settings/ssh_keys" ;;
	*)             URL="" ;;
esac
if [ -n "$URL" ]; then
	echo "Opening ${URL} ..."
	"${BROWSER:-xdg-open}" "$URL" >/dev/null 2>&1 || echo "  (open it manually: $URL)"
fi
authed() { ssh -o StrictHostKeyChecking=accept-new -T "git@${HOST}" 2>&1 | grep -qiE "authenticat|welcome to gitlab|logged in"; }
while ! authed; do
	printf 'Add the key above to %s, then press Enter to re-check (Ctrl-C to abort)... ' "$HOST"
	read -r _ || { echo "aborted"; exit 1; }
done
echo "SSH to ${HOST} works — you can clone private repos now."
EOF
RUN chmod +x /usr/local/bin/ncs-ssh-setup

# Add a CUSTOM SDK from any git manifest repo into the volume and register it for
# the extension. Run INSIDE the devcontainer terminal. For an SSH URL it first
# runs ncs-ssh-setup for that host (acquire key -> open page -> confirm), then
# clones — so a private repo (e.g. Bitbucket me/private-sdk-nrf) just works.
COPY <<'EOF' /usr/local/bin/ncs-add-sdk
#!/usr/bin/env bash
# Usage: ncs-add-sdk <name> <git-url> [revision] [toolchain-version] [manifest-file]
#   ncs-add-sdk private-sdk git@github.com:me/private-sdk-nrf.git main v3.3.0
set -eu
NAME="${1:?usage: ncs-add-sdk <name> <git-url> [rev] [toolchainVer] [manifestFile]}"
URL="${2:?usage: ncs-add-sdk <name> <git-url> [rev] [toolchainVer] [manifestFile]}"
REV="${3:-}"
TCV="${4:-v3.3.0}"
MF="${5:-}"
NCS_DIR="${NCS_INSTALL_DIR:-/root/ncs}"
DEST="${NCS_DIR}/${NAME}"

if [ -e "$DEST" ]; then
	echo "ncs-add-sdk: '$DEST' already exists — remove it or pick another name." >&2
	exit 1
fi

# Over SSH? Make sure SSH to that host is authorized first (guided).
case "$URL" in
	git@*:*) host="${URL#git@}"; host="${host%%:*}"; ncs-ssh-setup "$host" ;;
esac

INIT="west init -m \"$URL\""
[ -n "$REV" ] && INIT="$INIT --mr \"$REV\""
[ -n "$MF" ]  && INIT="$INIT --mf \"$MF\""
INIT="$INIT \"$DEST\""

echo "ncs-add-sdk: installing '$NAME' from $URL (rev=${REV:-default}, toolchain=$TCV)"
nrfutil toolchain-manager launch --ncs-version "$TCV" -- bash -lc \
	"$INIT && cd \"$DEST\" && west update && west zephyr-export"

ncs-register-sdks
echo "ncs-add-sdk: done. In the extension: Refresh SDKs, then Add build configuration"
echo "             with SDK='$NAME' and Toolchain=$TCV."
EOF
RUN chmod +x /usr/local/bin/ncs-add-sdk

WORKDIR /workspaces
CMD ["bash"]
