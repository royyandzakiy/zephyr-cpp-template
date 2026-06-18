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

### Host CLI — `scripts/ncs.py` (cross-platform: Linux / macOS / Windows)

One Python CLI for everything host-side (`python scripts/ncs.py <cmd> -h` for details).
Python is already required by the nRF/Zephyr ecosystem, so there's no new dependency.

| Command | Purpose |
|---|---|
| `build-image` | Build/refresh the `ncs-base` image and ensure the SDK volume. Run once. |
| `install-sdk v3.3.0` | Install an **official** NCS version (SDK + matching toolchain) into the volume via `nrfutil sdk-manager`. `--list` shows available/installed. |
| `install-custom-sdk <name> <git-url> [--rev …] [--toolchain …]` | Install a **custom** SDK via `west` from the host (public repos; private repos need the in-container `ncs-add-sdk`, which has the SSH key). |
| `shell [--ncs v3.3.0] [--sdk <folder>]` | Interactive shell with this project mounted and `ZEPHYR_BASE` set. |
| `build [--ncs v3.3.0] [--sdk <folder>] [--board …] [--pristine]` | Headless build. `--ncs` = toolchain; `--sdk` = which SDK folder (defaults to `--ncs`). |
| `flash [--serial …] [--hex …]` | Flash the built `.hex` from the **host** via `nrfutil device` (J-Link) — see §6. |

### Optional project file

| File | Purpose |
|---|---|
| [.devcontainer/setup-local.sh](.devcontainer/setup-local.sh) | **Optional, private-only.** First-time setup of the private `me/private-sdk-nrf` fork. The devcontainer runs it only if present, so **deleting this file removes private support entirely** (no other change). Edit the `SDK_URL`/`SDK_REV`/`TOOLCHAIN` vars at the top to point at a different repo/branch. |

---

## 4. Quick practical how-to

### One-time, on this machine

```bash
# 1. Build the small base image (+ create the SDK volume)
python scripts/ncs.py build-image

# 2. Install at least one official SDK version into the shared volume
python scripts/ncs.py install-sdk v3.3.0
python scripts/ncs.py install-sdk v3.2.4    # add as many as you like
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

```bash
python scripts/ncs.py build                          # v3.3.0, nRF5340 DK
python scripts/ncs.py build --ncs v3.2.4
python scripts/ncs.py build --sdk private-sdk --ncs v3.1.1   # custom SDK + its toolchain
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

## 6. Flashing & monitoring

Two interfaces matter on the J-Link, and they have very different needs:

| Task | Interface | Needs a kernel driver? |
|---|---|---|
| Flash, debug, **RTT monitor** | debug probe, via **libusb** | No — just USB access (`--privileged`) |
| UART console on `/dev/ttyACM*` | CDC-ACM VCOM | **Yes** — `cdc_acm` in the WSL2 kernel |

So **flashing and RTT monitoring work in the container**; only the VCOM serial
port needs a custom kernel — and **RTT replaces it**, so you don't need one.

### In the container (Windows + WSL2)

1. Forward the probe to WSL2 (this detaches it from Windows):
   ```powershell
   usbipd list                          # find the J-Link BUSID
   usbipd attach --wsl --busid <BUSID>
   ```
2. The devcontainer has `--privileged` + a whole-`/dev` bind (see
   `devcontainer.json` §`runArgs`/`mounts`), and the image bundles the **SEGGER
   J-Link runtime** (`libjlinkarm`) that `nrfutil device` needs — so the probe is
   both reachable *and* drivable. (Without that runtime you'd see "JLinkARM DLL
   not found" / "device cannot be recognized (NotFound)".)
3. **Flash**: the extension's Flash action, or in the terminal:
   ```bash
   west flash -d build
   ```
4. **Monitor — RTT (simplest)**: *nRF Connect: Connect to RTT* (or the RTT button
   on the build). RTT goes over the debug probe, so it needs nothing else.

#### Monitor over the UART VCOM (`/dev/ttyACM*`) instead of RTT

Only needed if you want the actual UART console (MCUboot serial recovery, a UART
shell, or firmware that logs only to UART). It needs the `cdc_acm` kernel module —
recent WSL2 kernels ship it. One-time per WSL session, **before** attaching:

```powershell
wsl -d <your-distro> -- sudo modprobe cdc_acm   # load it (kernel-global)
usbipd attach --wsl --busid <BUSID>             # node /dev/ttyACM* now appears
```
The whole-`/dev` mount means the container sees `/dev/ttyACM*` automatically. Open
it in the nRF Connect serial terminal (the nRF5340 DK app-core console is usually
**VCOM1 / `/dev/ttyACM1`**) at 115200, or `screen /dev/ttyACM1 115200`.

> If `modprobe cdc_acm` reports the module isn't found, your WSL2 kernel lacks it —
> run `wsl --update`, or build a custom kernel with `CONFIG_USB_ACM=y` and point
> `.wslconfig`'s `kernel=` at it. (You do **not** need to reinstall your distro —
> the kernel is shared across all WSL2 distros + Docker, independent of any distro.)

### From the host (fallback / simplest)

If you'd rather not juggle `usbipd` (you can't use the probe on Windows and in
WSL at the same time), build in the container and flash from the host:

```bash
python scripts/ncs.py flash                       # picks build/merged.hex
python scripts/ncs.py flash --serial 1050073602   # if more than one probe
```
That runs the host's `nrfutil device program` against the `.hex` in the
bind-mounted `build/` folder (needs `nrfutil` + J-Link drivers on the host). For
the UART console, open the J-Link VCOM port in a serial terminal.

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
| `scripts/ncs.py` | Cross-platform host CLI: build/install/shell/flash (see §3). |
| `.clang-format`, `.clang-tidy`, `.cmake-format.yaml`, `.vscode/settings.json` | Formatting/lint/IntelliSense config. |
| `.gitattributes` | Forces `*.sh` to LF (they run in Linux). |

---

## 8. Starting a new project from this template

1. Copy the whole folder to a new name.
2. (Optional) rename `project()` in `CMakeLists.txt`.
3. Don't need private? Delete `.devcontainer/setup-local.sh`.
4. **Reopen in Container.** It attaches to the same `ncs-base` image and the same
   `ncs-sdks` volume — no SDK re-download. Pick an SDK in the extension and build.
