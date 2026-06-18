# zephyr-cpp-template

A copy-me template for **nRF Connect SDK (NCS) C++ applications** that develop in
a **Docker dev container** while keeping the multi-GB SDK out of every project.

The SDKs and toolchains live **once** in a shared Docker volume; every project
reuses them and only mounts its own source. You can hold **many SDK versions
side-by-side** (official *and* custom forks) and pick one per build configuration
in the nRF Connect for VS Code extension — exactly like a native install.

---

## 1. How it's put together

```
┌─ ncs-base : Docker IMAGE ────────────────┐   small, version-agnostic.
│  host tools + nrfutil + helper commands  │   built ONCE, shared by every project.
└──────────────────────────────────────────┘
                 │ uses
                 ▼
┌─ ncs-sdks : Docker VOLUME  → /root/ncs ──┐   the SDK store. all versions +
│  toolchains/  v3.3.0/  v3.2.4/  private-sdk/│   toolchains. shared, persistent.
└──────────────────────────────────────────┘
┌─ ncs-ssh  : Docker VOLUME  → /root/.ssh ─┐   your SSH key (add to Git host once).
└──────────────────────────────────────────┘
                 │ + bind-mount
                 ▼
┌─ your project  → /workspaces/<name> ─────┐   freestanding app. CMakeLists/prj.conf/
│  CMakeLists.txt  prj.conf  src/main.cpp  │   src — NOT inside the SDK tree.
└──────────────────────────────────────────┘
```

Why this shape:

- **Image stays tiny** — it has *no* SDK, so it rarely changes and copies instantly.
- **SDKs are a volume, not image layers** — installed once with `nrfutil`/`west`,
  reused by every container and project, and you add/remove versions with **no
  image rebuild**.
- **Projects are freestanding** — nothing in a project pins an SDK version; the
  build configuration you pick in the extension decides. That's what makes
  switching versions clean.

---

## 2. The one thing that's non-obvious: how the extension *finds* SDKs

The nRF Connect extension discovers toolchains and SDKs through **two separate
mechanisms**, and both have to point at `/root/ncs`. This is the part that took
the most digging, so it's documented here explicitly.

| What | How the extension finds it | What makes it work here |
|---|---|---|
| **Toolchains** | runs `nrfutil toolchain list --install-dir <dir>` | the setting **`nrf-connect.toolchainManager.installDirectory` = `/root/ncs`** in `devcontainer.json` |
| **SDKs** | reads the **CMake user package registry** `~/.cmake/packages/Zephyr` (where `west zephyr-export` registers Zephyr) | **`ncs-register-sdks`** run on every start via `postStartCommand` |

So if the extension ever says **"SDK not configured"** or a version is missing:

1. **Toolchain missing?** → check the `installDirectory` setting (see below).
2. **SDK missing?** → the CMake registry wasn't populated. Re-run `ncs-register-sdks`
   in the terminal, then **nRF Connect: Refresh SDKs** (or reload the window).
   `~/.cmake` is ephemeral, which is exactly why `postStartCommand` re-runs it
   every start.

### Where to change registration

| To change… | Edit… |
|---|---|
| The install dir the extension uses | `nrf-connect.toolchainManager.installDirectory` in [.devcontainer/devcontainer.json](.devcontainer/devcontainer.json) (and the volume mount target + `NCS_INSTALL_DIR` in the [Dockerfile](Dockerfile) if you move it off `/root/ncs`) |
| When SDKs get registered | `postStartCommand` in [.devcontainer/devcontainer.json](.devcontainer/devcontainer.json) |
| *Which* folders count as SDKs | the `ncs-register-sdks` script (baked in the [Dockerfile](Dockerfile)) — it registers any folder under `/root/ncs` containing `zephyr/share/zephyr-package/cmake` |

---

## 3. What each script does

### Baked into the image (on `PATH` in every container)

| Command | Purpose |
|---|---|
| `ncs-register-sdks` | Registers **every** west workspace in `/root/ncs` (official + custom, any folder name) into the CMake package registry so the extension lists them. Run automatically by `postStartCommand`. |
| `ncs-ssh-key [--new]` | Ensures an SSH key exists and prints the **public** key. Reuses the existing key (persisted in the `ncs-ssh` volume); `--new` forces a fresh one. Run by `postCreateCommand`. |
| `ncs-ssh-setup <host>` | **Guided** SSH authorization: ensure key → open the host's SSH-keys page in your browser → wait while you add it → verify `ssh -T`. Hosts: `bitbucket.org`, `github.com`, `gitlab.com`. |
| `ncs-add-sdk <name> <git-url> [rev] [toolchain] [manifest-file]` | Installs any custom SDK from a git manifest repo into the volume and registers it. For an SSH URL it runs `ncs-ssh-setup` first. Run it in the devcontainer terminal. |

### Host PowerShell scripts (`scripts/`) — for use *without* VS Code

| Script | Purpose |
|---|---|
| `build-image.ps1 [-NcsRev v3.3.0]` | Build/refresh the `ncs-base` image. Run once. |
| `install-sdk.ps1 -NcsRev v3.3.0` | Install an **official** NCS version (SDK + matching toolchain) into the volume via `nrfutil sdk-manager`. `-List` to see what's available/installed. |
| `install-custom-sdk.ps1 -Name … -ManifestUrl … [-Rev …] [-ToolchainVer …]` | Install a **custom** SDK via `west` from the host (works for public repos; private repos need the in-container `ncs-add-sdk` which has the SSH key). |
| `shell.ps1 [-NcsRev v3.3.0] [-Sdk <folder>]` | Interactive shell with this project mounted and `ZEPHYR_BASE` set. |
| `build.ps1 [-NcsRev v3.3.0] [-Sdk <folder>] [-Board …] [-Pristine]` | Headless build. `-NcsRev` = toolchain; `-Sdk` = which SDK folder (defaults to `-NcsRev`). |
| `flash.ps1 [-SerialNumber …] [-Hex …]` | Flash the built `.hex` from the **host** via `nrfutil device` (reliable on Windows — see §6). |

### Optional project file

| File | Purpose |
|---|---|
| [.devcontainer/setup-local.sh](.devcontainer/setup-local.sh) | **Optional, private-only.** First-time setup of the private `me/private-sdk-nrf` fork. The devcontainer runs it only if present, so **deleting this file removes private support entirely** (no other change). Edit the `SDK_URL`/`SDK_REV`/`TOOLCHAIN` vars at the top to point at a different repo/branch. |

---

## 4. Quick practical how-to

### One-time, on this machine

```powershell
# 1. Build the small base image
./scripts/build-image.ps1

# 2. Install at least one official SDK version into the shared volume
./scripts/install-sdk.ps1 -NcsRev v3.3.0
./scripts/install-sdk.ps1 -NcsRev v3.2.4    # add as many as you like
```

### Open the project

VS Code → **Dev Containers: Rebuild and Reopen in Container**. On first creation:

- your SSH **public key** is printed in the creation log
  (View → *Dev Containers: Show Container Log*),
- if `setup-local.sh` is present, you'll be told to run it (see below).

Then **nRF Connect → Add build configuration**: pick an **SDK version** and
**toolchain** (e.g. `v3.3.0`), board `nrf5340dk/nrf5340/cpuapp`, and build.

### Build from the integrated terminal

```bash
west build -b nrf5340dk/nrf5340/cpuapp .
```

### Build headless (no VS Code)

```powershell
./scripts/build.ps1                         # v3.3.0, nRF5340 DK
./scripts/build.ps1 -NcsRev v3.2.4
./scripts/build.ps1 -Sdk private-sdk -NcsRev v3.1.1   # custom SDK + its toolchain
```

### Switch SDK versions

Just add another build configuration in the extension and pick a different SDK +
toolchain. They sit side-by-side, each with its own build dir. Nothing in the
project pins a version.

### Add a custom / forked / private SDK

Install the toolchain it's based on first if you don't have it
(`nrfutil toolchain-manager install --ncs-version vX.Y.Z` in the terminal), then:

```bash
# in the devcontainer terminal — guided SSH for private repos, then clones:
ncs-add-sdk my-sdk git@github.com:me/sdk-nrf-fork.git my-branch v3.3.0
```
Use the git **clone** URL (not the browser `/src/...` URL). After it finishes:
**Refresh SDKs** → it appears as `my-sdk` in *Add build configuration*.

### private SDK (internal)

`.devcontainer/setup-local.sh` is pre-wired for `me/private-sdk-nrf` (branch
`main`, toolchain `v3.1.1`). On first open you'll be prompted; in the
terminal run:

```bash
nrfutil toolchain-manager install --ncs-version v3.1.1   # once, if not installed
bash .devcontainer/setup-local.sh                           # SSH key → Bitbucket → clone
```
Don't need it? **Delete `.devcontainer/setup-local.sh`** — the devcontainer simply
skips it.

---

## 5. The C++ application

A bare C++23 blinky for the nRF5340 DK ([src/main.cpp](src/main.cpp)). The
non-obvious part of getting C++ to build on Zephyr is the Kconfig in
[prj.conf](prj.conf):

```
CONFIG_CPP=y
CONFIG_STD_CPP2B=y        # C++23
CONFIG_GLIBCXX_LIBCPP=y   # full libstdc++ → std::array/string_view/variant/...
CONFIG_CPP_RTTI=y
CONFIG_NEWLIB_LIBC=y      # libc backing the C++ runtime/heap
CONFIG_HEAP_MEM_POOL_SIZE=8192
```

No `boards/` overlay is needed for the bare nRF5340 DK — `led0` comes from the
in-tree board devicetree. Add a `boards/` folder only for custom-board overlays.

---

## 6. Flashing

**Build in the container, flash from the Windows host.** This is the reliable
workflow on Windows. A helper does it for you:

```powershell
./scripts/flash.ps1                       # picks build\merged.hex automatically
./scripts/flash.ps1 -SerialNumber 1050073602   # if more than one probe
```
It runs the host's `nrfutil device program` (J-Link) against the `.hex` in the
bind-mounted `build/` folder. Or use the **nRF Connect Programmer** GUI / the
host's nRF Connect extension. For the console, open the J-Link **VCOM COM port**
in a Windows serial terminal (e.g. nRF Connect Serial Terminal).

### Why not flash from inside the container?

On Windows the container runs under WSL2, and USB reaches it only via
`usbipd-win`. Even after `usbipd attach` (so `lsusb` *does* show the J-Link),
two things break:

- **No `/dev/ttyACM*`** — the J-Link VCOM needs the `cdc_acm` driver bound in the
  *WSL2 kernel*, which the stock kernel doesn't do. So the extension's serial
  monitor fails with `cannot open /dev/ttyACM1`.
- **`west flash` fails** with `operation not available for the selected device
  (NotFound)` — `nrfutil`'s J-Link backend can't reliably drive the probe over
  USB/IP, even though the device enumerates.

Neither is a problem with this template (your build is fine) — it's USB
passthrough on Windows. Flashing from the host sidesteps both. (On a **Linux
host**, in-container flashing *can* work: add `"runArgs": ["--privileged"]` and
mount `/dev/bus/usb` in `devcontainer.json` — ask if you want that wired in.)

---

## 7. File map

| Path | What |
|---|---|
| `Dockerfile` | Builds `ncs-base` (host tools + nrfutil + the `ncs-*` helper commands). |
| `.dockerignore` | Keeps the image build context empty (no SDK, no source). |
| `.devcontainer/devcontainer.json` | Image ref, volume mounts, workspace bind, extension list, the `installDirectory` setting, `postCreate`/`postStart` commands. |
| `.devcontainer/setup-local.sh` | Optional, deletable private first-time SDK setup. |
| `CMakeLists.txt`, `prj.conf`, `src/main.cpp` | The freestanding C++23 app. |
| `sample.yaml` | Twister build test (`west twister -T .`). |
| `debug-overlay.conf` | Extra debug Kconfig (`-DEXTRA_CONF_FILE=...`). |
| `scripts/*.ps1` | Host-side build/install helpers (see §3). |
| `.clang-format`, `.clang-tidy`, `.cmake-format.yaml`, `.vscode/settings.json` | Formatting/lint/IntelliSense config. |
| `.gitattributes` | Forces `*.sh` to LF (they run in Linux). |

---

## 8. Starting a new project from this template

1. Copy the whole folder to a new name.
2. (Optional) rename `project()` in `CMakeLists.txt`.
3. Don't need private? Delete `.devcontainer/setup-local.sh`.
4. **Reopen in Container.** It attaches to the same `ncs-base` image and the same
   `ncs-sdks` volume — no SDK re-download. Pick an SDK in the extension and build.
