# syntax=docker/dockerfile:1

# ncs-base: a small, version-agnostic Zephyr / nRF Connect SDK build image.
#
# Holds host tools and nrfutil only, no SDK. SDKs and toolchains go into a Docker
# volume mounted at /root/ncs, so the image rarely changes, many SDK versions sit side
# by side, and every project shares them. See docs/setup/devcontainer.md.
#
# Build for amd64 (nrfutil, the Zephyr SDK and J-Link are x86_64 only):
#   docker build --platform=linux/amd64 -t ncs-base:latest .devcontainer
# Apple Silicon and arm64 Linux then run it under emulation. The platform is passed at
# build time rather than in FROM, which BuildKit's lint rejects.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# The SDK store. Must be /root/ncs, the nRF Connect extension's own install dir (~/ncs),
# which it uses regardless of nrfutil's config. Change it together with the volume
# mount and installDirectory in devcontainer.json.
ENV NCS_INSTALL_DIR=/root/ncs

# nrfutil's toolchain bundles ship their own cmake, ninja, python and west, so the
# host layer only needs git, libusb and the basics.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl wget git openssh-client \
      python3 python3-venv \
      file xz-utils libusb-1.0-0 \
      usbutils \
      iwyu \
    && rm -rf /var/lib/apt/lists/*

# NCS v2.4.0's bundled git links against libunistring.so.2, but Ubuntu 24.04
# (noble) ships libunistring.so.5. Symlink so the old toolchain's git can load it.
RUN ln -sf /usr/lib/x86_64-linux-gnu/libunistring.so.5 \
           /usr/lib/x86_64-linux-gnu/libunistring.so.2

# nrfutil plus the sub-commands the extension uses.
RUN curl -fsSL \
      https://files.nordicsemi.com/artifactory/swtools/external/nrfutil/executables/x86_64-unknown-linux-gnu/nrfutil \
      -o /usr/local/bin/nrfutil \
    && chmod +x /usr/local/bin/nrfutil \
    && nrfutil install toolchain-manager \
    && nrfutil install sdk-manager \
    && nrfutil install device || true

# SEGGER J-Link runtime: `nrfutil device` needs libjlinkarm to flash or debug, and
# fails with "JLinkARM DLL not found" without it. Uses the headless .tgz, since the
# .deb depends on Qt4, which Ubuntu 24.04 does not ship.
# The tarball ships 64-bit and 32-bit libs under the same soname, and ldconfig over
# its dir picks the 32-bit one, which then fails to load. So only the 64-bit lib is
# registered, from a dir of its own.
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

# Points both nrfutil managers at the store, so CLI installs land where the extension
# looks for toolchains (its installDirectory setting).
RUN mkdir -p ${NCS_INSTALL_DIR} \
    && nrfutil sdk-manager config install-dir set ${NCS_INSTALL_DIR} \
    && nrfutil toolchain-manager config --set install-dir=${NCS_INSTALL_DIR}

# The extension finds SDKs in the CMake package registry (~/.cmake/packages/Zephyr),
# which nrfutil does not populate and which is lost with the container layer. So this
# re-creates the entries for every SDK in the store, on each start (postStartCommand).
COPY <<'EOF' /usr/local/bin/ncs-register-sdks
#!/usr/bin/env bash
# Registers every Zephyr workspace in the store, whatever its folder name. A folder
# counts if it has zephyr/share/zephyr-package/cmake.
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

# ncs-ssh-key [--new]: ensures an SSH key exists and prints its public part. Reuses the
# key in the ncs-ssh volume so it survives rebuilds; --new forces a fresh one.
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
echo "  SSH PUBLIC KEY, add it to your Git host to clone private repos:"
echo "------------------------------------------------------------------"
cat "${KEY}.pub"
echo "=================================================================="
EOF
RUN chmod +x /usr/local/bin/ncs-ssh-key

# ncs-ssh-setup <host>: ensures a key, opens the host's SSH-keys page ($BROWSER is wired
# to the host by VS Code), then re-checks `ssh -T` until the key is accepted.
COPY <<'EOF' /usr/local/bin/ncs-ssh-setup
#!/usr/bin/env bash
set -eu
HOST="${1:-github.com}"
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
echo "SSH to ${HOST} works, you can clone private repos now."
EOF
RUN chmod +x /usr/local/bin/ncs-ssh-setup

# ncs-add-sdk <name> <git-url> [rev] [toolchain] [manifest]: installs a custom SDK from
# any west manifest repo into the volume and registers it. For an SSH URL it runs
# ncs-ssh-setup for that host first, so private repos clone without extra steps.
COPY <<'EOF' /usr/local/bin/ncs-add-sdk
#!/usr/bin/env bash
# Usage: ncs-add-sdk <name> <git-url> [revision] [toolchain-version] [manifest-file]
#   ncs-add-sdk my-sdk git@github.com:you/sdk-nrf-fork.git main v3.3.0
set -eu
NAME="${1:?usage: ncs-add-sdk <name> <git-url> [rev] [toolchainVer] [manifestFile]}"
URL="${2:?usage: ncs-add-sdk <name> <git-url> [rev] [toolchainVer] [manifestFile]}"
REV="${3:-}"
TCV="${4:-v3.3.0}"
MF="${5:-}"
NCS_DIR="${NCS_INSTALL_DIR:-/root/ncs}"
DEST="${NCS_DIR}/${NAME}"

if [ -e "$DEST" ]; then
	echo "ncs-add-sdk: '$DEST' already exists, remove it or pick another name." >&2
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
