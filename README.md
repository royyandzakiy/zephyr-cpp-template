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
./scripts/build-image.ps1                  # latest SDK (main branch)
# or pin a release for reproducibility:
./scripts/build-image.ps1 -NcsRev v2.9.0
```

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
| `CMakeLists.txt`, `prj.conf`, `src/main.cpp` | The bare C++ blinky app |
| `scripts/build-image.ps1` | Build/refresh the shared image |
| `scripts/shell.ps1` | Interactive shell with this project mounted |
| `scripts/build.ps1` | One-shot headless build |
