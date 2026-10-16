# zephyr-cpp-template

[![CI](https://github.com/royyandzakiy/zephyr-cpp-template/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/royyandzakiy/zephyr-cpp-template/actions/workflows/ci.yml)
![C++23](https://img.shields.io/badge/C%2B%2B-23-blue)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

A copy-me template for **Zephyr and nRF Connect SDK (NCS) C++ applications** that are
developed in a **Docker devcontainer**, while the multi-GB SDKs stay out of every
project.

The SDKs and toolchains live **once**, in a shared Docker volume or a plain directory
such as `~/ncs`. Every project reuses them and only mounts its own source. Many SDK
versions sit side by side (official NCS, upstream Zephyr, and your own forks), and each
build configuration in the nRF Connect for VS Code extension picks one, exactly like a
native install.

## Repository structure

```
.
├── src/main.cpp            the app: a C++23 blinky that logs each LED transition
├── boards/                 per-board Kconfig and overlays, merged in by board name
├── CMakeLists.txt, prj.conf
├── sample.yaml             Twister scenarios: build for the Nordic DKs, run on native_sim
├── debug-overlay.conf      extra debug Kconfig (-DEXTRA_CONF_FILE=debug-overlay.conf)
├── scripts/ncs.py          one CLI to install, register, build and flash against any SDK
├── docs/                   everything beyond the quick start, indexed in docs/README.md
├── .devcontainer/          the container: devcontainer.json plus the Dockerfile it builds
├── .github/workflows/      CI: format check and Twister on native_sim and the Nordic DKs
└── .clang-format, .clang-tidy, .clangd, .editorconfig, .vscode/
```

## Quick start

You need **Docker** and **Python 3** on the host. Windows 11, Linux and macOS (Intel and
Apple Silicon) all build the same way; only flashing differs, see
[`docs/setup/flash-monitor.md`](docs/setup/flash-monitor.md).

```bash
# Build the base image and create the SDK volume. Optional: opening the devcontainer
# builds it too.
python scripts/ncs.py build-image

# Install at least one SDK into the volume, as many versions as you like.
python scripts/ncs.py --docker install ncs v3.3.0
python scripts/ncs.py --docker install vanilla v4.2.2
```

Then in VS Code, **Dev Containers: Rebuild and Reopen in Container**, and
**nRF Connect: Add build configuration** with an SDK, its toolchain and a board. Or
from the container terminal:

```bash
west build -b nrf5340dk/nrf5340/cpuapp .
```

Prefer no Docker, with the store in WSL or Linux under `~/ncs`? It is the same CLI
without `--docker`, see [`docs/ncs-cli.md`](docs/ncs-cli.md).

## The app

[`src/main.cpp`](src/main.cpp) toggles `led0` once a second and logs `LED on` /
`LED off`. It uses a little of the STL so the C++ Kconfig in [`prj.conf`](prj.conf) is
exercised by a real build:

```
CONFIG_CPP=y
CONFIG_STD_CPP2B=y             # C++23
CONFIG_REQUIRES_FULL_LIBCPP=y  # full C++ library: libstdc++ on cross toolchains, the host's on native_sim
CONFIG_CPP_RTTI=y
```

`prj.conf` holds nothing board-specific, so the same source builds for any board.
Board-specific options live in `boards/`, which Zephyr merges in by board name:

| | |
|---|---|
| `nrf5340dk_nrf5340_cpuapp.conf`, `nrf52840dk_nrf52840.conf` | RTT log backend, so logs are readable over the J-Link from inside the container |
| `native_sim_native.overlay` | puts `led0` on the GPIO emulator, since native_sim has no LED |

## Tests and CI

[`sample.yaml`](sample.yaml) has two Twister scenarios: a build for the nRF5340 and
nRF52840 DKs, and a native_sim run that checks the log. The same command runs locally
and in CI:

```bash
west twister -T . -p native_sim -p nrf5340dk/nrf5340/cpuapp -O /tmp/tw --clobber-output
```

`-O /tmp/tw --clobber-output` keeps Twister's output inside the container. Twister
rotates `twister-out/` on every run, and that rotation fails on a Windows bind mount.

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push and pull
request: a `clang-format` and Python check, then Twister in a container with upstream
Zephyr baked in. No hardware needed.

## Starting a new project from this template

1. **Use this template** on GitHub, or copy the folder.
2. Rename `project()` in [`CMakeLists.txt`](CMakeLists.txt) and the scenarios in
   [`sample.yaml`](sample.yaml).
3. **Reopen in Container.** It reuses the same image and the same SDK volume, so
   nothing downloads again. Pick an SDK in the extension and build.

For private or internal setup, such as installing a private SDK fork on first start,
drop a gitignored `.devcontainer/setup-local.sh`, see
[`docs/setup/devcontainer.md`](docs/setup/devcontainer.md#4-optional-a-local-first-time-setup-hook).
`.devcontainer/` also works on its own in any other Zephyr project.

## Documentation

[`docs/README.md`](docs/README.md) is the index. [`CONTRIBUTING.md`](CONTRIBUTING.md)
covers code style and what to check before a pull request.
