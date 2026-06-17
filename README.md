# zephyr-cpp-template

A copy-me template for nRF Connect SDK (NCS) C++ applications. The nRF SDK is
downloaded **once** into a shared Docker image; every project you spin off from
this template reuses that same image and only mounts its own source — so you
never re-download the multi-GB SDK per project.

## How it works

```
ncs-workspace:latest  (Docker image, built once)
└── /workspace/                 ← west workspace, SDK baked in
    ├── zephyr/ nrf/ modules/   ← the heavy SDK (lives in the image)
    └── projects/
        └── <your-project>/     ← YOUR source, bind-mounted at runtime
```

- **`Dockerfile`** builds the shared `ncs-workspace` image: it runs
  `west init` against `sdk-nrf`, `west update`, and `west sdk install`. This is
  the only step that touches the network.
- **`.devcontainer/`** and **`scripts/`** both point at that pre-built image and
  bind-mount the current project into `/workspace/projects/<folder-name>`.

Copying this template gives you a new folder with the same `Dockerfile` and
configs. Because they reference the image **by tag** (`ncs-workspace:latest`),
the new project just attaches to the image you already have. No re-download.

## One-time setup

Build the shared image once (takes a while — it pulls the whole SDK):

```powershell
./scripts/build-image.ps1                  # NCS v3.3.0 (matches the reference project)
# or track the bleeding edge:
./scripts/build-image.ps1 -NcsRev main
```

> The default pins **NCS v3.3.0** — the same release `balancer-robot-fw` is known
> to build with, so the C++23 + STL setup is guaranteed to work. Bump it when you're
> ready to move.

This produces the `ncs-workspace:latest` image. Every project from now on reuses it.

## Per-project workflow

### Option A — VS Code Dev Container (gets the Nordic extensions)

1. Open this folder in VS Code.
2. *Reopen in Container* (Dev Containers extension). It attaches to
   `ncs-workspace:latest` and mounts this folder into
   `/workspace/projects/<folder-name>`.
3. In the integrated terminal:
   ```bash
   west build -b nrf5340dk/nrf5340/cpuapp .
   ```

### Option B — plain Docker (no VS Code)

```powershell
./scripts/build.ps1            # one-shot build for the nRF5340 DK
# or drop into a shell:
./scripts/shell.ps1
#   west build -b nrf5340dk/nrf5340/cpuapp .
```

Build artifacts land in `./build/` on your host (the folder is bind-mounted).

## Flashing

Flashing/debugging over J-Link USB **from inside a container does not work
cleanly on Windows** (Docker Desktop/WSL2 USB passthrough). Build in the
container, then flash from the Windows host:

```powershell
nrfutil device program --firmware build/zephyr/zephyr.hex --options reset=RESET_SYSTEM
# or with the J-Link / nRF Connect Programmer GUI
```

## Starting a new project

1. Copy this whole folder to a new name, e.g. `my-sensor`.
2. (Optional) rename the CMake `project()` in `CMakeLists.txt`.
3. Open it / run the scripts. It binds to the same image — instant, no download.

## Targeting a different board

Change the `-b` argument, e.g. `-b nrf52840dk/nrf52840`. If the board needs a
toolchain other than ARM, rebuild the image with
`--build-arg ZEPHYR_TOOLCHAINS=all`.

## Files

| Path | Purpose |
|---|---|
| `Dockerfile` | Builds the shared SDK workspace image (run once) |
| `.devcontainer/devcontainer.json` | VS Code attaches to the image + Nordic extensions |
| `CMakeLists.txt`, `prj.conf`, `src/main.cpp` | The bare C++23 blinky app |
| `sample.yaml` | Twister build test (`west twister -T .`) |
| `debug-overlay.conf` | Extra debug Kconfig (`-DEXTRA_CONF_FILE=...`) |
| `.clang-format`, `.clang-tidy`, `.cmake-format.yaml` | Formatting/lint config (from the reference) |
| `.vscode/settings.json` | C++23 IntelliSense + clang-tidy |
| `scripts/build-image.ps1` | Build/refresh the shared image |
| `scripts/shell.ps1` | Interactive shell with this project mounted |
| `scripts/build.ps1` | One-shot headless build |

## C++ Kconfig notes

The C++ support in `prj.conf` mirrors the reference project — the non-obvious part
of getting C++ to build on Zephyr:

```
CONFIG_CPP=y
CONFIG_STD_CPP2B=y        # C++23
CONFIG_GLIBCXX_LIBCPP=y   # full libstdc++ → std::array/string_view/variant/...
CONFIG_CPP_RTTI=y
CONFIG_NEWLIB_LIBC=y      # libc that backs the C++ runtime/heap
CONFIG_HEAP_MEM_POOL_SIZE=8192
```

No `boards/` overlay is needed for the bare nRF5340 DK build — `led0` comes from
the in-tree board devicetree. Add a `boards/` folder only when you need pin/peripheral
overlays for a custom board.
