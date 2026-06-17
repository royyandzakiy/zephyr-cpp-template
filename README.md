# zephyr-cpp-template

A copy-me template for nRF Connect SDK (NCS) C++ applications.

SDK versions are managed by **nrfutil** (the same tool the nRF Connect for VS Code
extension uses) and stored in a shared **Docker volume**, so:

- many NCS versions live side-by-side and you pick which to build with — per project,
  in the extension
- each version is downloaded **once** and reused by every project and every container
- the Docker image stays tiny; you add/remove SDK versions with nrfutil, no rebuild

## How it works

Three separate pieces, each with one job:

```
ncs-base:latest            (Docker image)   host tools + nrfutil only — small, stable
        │
        │ runs, mounting ▼
ncs-sdks                   (Docker volume)  the SDK STORE, shared by everything:
  /opt/nordic/ncs/
  ├── toolchains/<bundle>/      one matching toolchain per version
  ├── v3.3.0/                   full west workspace
  └── v3.2.4/                   full west workspace
        │
        │ + bind-mount ▼
<your-repo>/               (this folder)    a FREESTANDING app — builds against
  CMakeLists.txt                            whichever SDK version you select; it does
  prj.conf                                  NOT live inside the SDK tree
  src/main.cpp
```

This is the same layout as a native Windows install (`C:\ncs\v3.3.0`,
`C:\ncs\toolchains\...`), which is exactly what the extension auto-discovers.

## One-time setup (per machine)

```powershell
# 1. Build the small base image + create the shared volume
./scripts/build-image.ps1

# 2. Install the SDK version(s) you want into the volume (downloads once each)
./scripts/install-sdk.ps1 -NcsRev v3.3.0
./scripts/install-sdk.ps1 -NcsRev v3.2.4

# See what's available / installed
./scripts/install-sdk.ps1 -List
```

You can also install versions later from the extension's **Manage SDKs / Manage
toolchains** UI inside the dev container — they go into the same volume.

## Per-project workflow

### Option A — VS Code Dev Container (recommended; full extension UX)

1. Open this folder in VS Code → *Reopen in Container*. It attaches to
   `ncs-base:latest` and mounts the shared `ncs-sdks` volume.
2. In the **nRF Connect** view, *Add build configuration* → pick the **SDK
   version**, **toolchain**, and **board** (`nrf5340dk/nrf5340/cpuapp`) → Build.
3. Switch versions anytime by adding another build configuration with a different
   SDK version. Both stay side-by-side.

### Option B — plain Docker (no VS Code)

```powershell
./scripts/build.ps1                     # v3.3.0, nRF5340 DK
./scripts/build.ps1 -NcsRev v3.2.4      # build the SAME project against another version
./scripts/shell.ps1 -NcsRev v3.3.0      # interactive; then: west build -b nrf5340dk/nrf5340/cpuapp .
```

Artifacts land in `./build/` on the host (the folder is bind-mounted).

## Switching SDK versions

The whole point of this layout: the project is freestanding, so the **only** thing
that selects the SDK is the version you point at.

- **Extension:** choose the SDK version in the build configuration.
- **Scripts:** pass `-NcsRev v3.x.y`.

Both `v3.3.0` and `v3.2.4` are installed and verified to build this template.

## Flashing

Flashing over J-Link USB from inside a container is not practical on Windows
(Docker Desktop/WSL2 USB passthrough). Build in the container, then flash from the
Windows host:

```powershell
nrfutil device program --firmware build/<project>/zephyr/zephyr.hex --options reset=RESET_SYSTEM
# or the nRF Connect Programmer / J-Link GUI
```

## Starting a new project

1. Copy this whole folder to a new name, e.g. `my-sensor`.
2. (Optional) rename the CMake `project()` in `CMakeLists.txt`.
3. Open it / run the scripts. It attaches to the same image and the same SDK
   volume — instant, no downloads.

## C++ Kconfig notes

The C++ support in `prj.conf` mirrors the reference project (`balancer-robot-fw`) —
the non-obvious part of getting C++ to build on Zephyr:

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

## Files

| Path | Purpose |
|---|---|
| `Dockerfile` | Builds the small `ncs-base` image (host tools + nrfutil) |
| `.devcontainer/devcontainer.json` | Attaches to the image + mounts the SDK volume + Nordic extensions |
| `CMakeLists.txt`, `prj.conf`, `src/main.cpp` | The bare C++23 blinky app (freestanding) |
| `sample.yaml` | Twister build test |
| `debug-overlay.conf` | Extra debug Kconfig (`-DEXTRA_CONF_FILE=...`) |
| `.clang-format`, `.clang-tidy`, `.cmake-format.yaml` | Formatting/lint config (from the reference) |
| `.vscode/settings.json` | C++23 IntelliSense + clang-tidy |
| `scripts/build-image.ps1` | Build base image + create the SDK volume (once) |
| `scripts/install-sdk.ps1` | Install/list NCS versions in the shared volume |
| `scripts/build.ps1` | Headless build against a chosen version |
| `scripts/shell.ps1` | Interactive shell for a chosen version |
