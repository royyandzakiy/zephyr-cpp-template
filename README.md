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
│  toolchains/  v3.3.0/  v3.2.4/  my-sdk/  │   toolchains. shared, persistent.
└──────────────────────────────────────────┘   (or a plain dir, e.g. ~/ncs in WSL)
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
mechanisms**, and both have to point at the same **store** directory (the volume
target `/root/ncs` in the container, or e.g. `~/ncs` natively in WSL). This is the
part that took the most digging, so it's documented here explicitly.

| What | How the extension finds it | What makes it work here |
|---|---|---|
| **Toolchains** | runs `nrfutil toolchain list --install-dir <dir>` | the setting **`nrf-connect.toolchainManager.installDirectory` = the store** — in `devcontainer.json`, or written by `ncs.py register --vscode` |
| **SDKs** | reads the **CMake user package registry** `~/.cmake/packages/Zephyr` (where `west zephyr-export` registers Zephyr) | **`ncs.py register`** — run by every install, and on every container start via `postStartCommand` |

So if the extension ever says **"SDK not configured"** or a version is missing,
run `python3 scripts/ncs.py doctor` — it checks both mechanisms and reports which
one is wrong. The fix is almost always:

```bash
python3 scripts/ncs.py register --vscode
```

then **nRF Connect: Refresh SDKs** (or reload the window). `~/.cmake` is
ephemeral in a container, which is exactly why `postStartCommand` re-registers on
every start.

### Where to change registration

| To change… | Edit… |
|---|---|
| Where the store is, natively | `python3 scripts/ncs.py config set install-dir ~/ncs` — see [docs/ncs-cli.md](docs/ncs-cli.md) §3 |
| Where the store is, in the container | `nrf-connect.toolchainManager.installDirectory` in [.devcontainer/devcontainer.json](.devcontainer/devcontainer.json), the volume mount target there, and `NCS_INSTALL_DIR` in the [.devcontainer/Dockerfile](.devcontainer/Dockerfile) — all three together |
| When SDKs get registered | `postStartCommand` in [.devcontainer/devcontainer.json](.devcontainer/devcontainer.json) |
| *Which* folders count as SDKs | `scripts/ncs.py register` (and the baked-in `ncs-register-sdks`) — any folder in the store containing `zephyr/share/zephyr-package/cmake`, whatever its name |

---

## 3. What each script does

### Baked into the image (on `PATH` in every container)

| Command | Purpose |
|---|---|
| `ncs-register-sdks` | Registers **every** west workspace in `/root/ncs` (official + custom, any folder name) into the CMake package registry so the extension lists them. Run automatically by `postStartCommand`. |
| `ncs-ssh-key [--new]` | Ensures an SSH key exists and prints the **public** key. Reuses the existing key (persisted in the `ncs-ssh` volume); `--new` forces a fresh one. Run by `postCreateCommand`. |
| `ncs-ssh-setup <host>` | **Guided** SSH authorization: ensure key → open the host's SSH-keys page in your browser → wait while you add it → verify `ssh -T`. Hosts: `bitbucket.org`, `github.com`, `gitlab.com`. |
| `ncs-add-sdk <custom-folder-name> <git-url> [branch] [toolchain] [manifest-file]` | Installs any custom SDK from a git manifest repo into the volume and registers it. For an SSH URL it runs `ncs-ssh-setup` first. Run it in the devcontainer terminal. |

### `scripts/ncs.py` — the one CLI (full guide: [docs/ncs-cli.md](docs/ncs-cli.md))

One Python file installs, registers and uses every kind of SDK — official NCS,
vanilla Zephyr, and custom/forked/private — plus their toolchains. It runs
natively (WSL/Linux/macOS, no root, store in `~/ncs`), inside the devcontainer,
or against the Docker volume from a Windows/macOS host (`--docker`).

| Command | Purpose |
|---|---|
| `bootstrap` | Download `nrfutil` into `~/.local/bin` + its sub-commands. No root. |
| `config show \| set <key> <value>` | Where the store lives (`install-dir`) and other defaults. |
| `install ncs v3.3.0` | Official NCS: toolchain + `sdk-nrf` workspace + registration. |
| `install vanilla v4.2.2` | Upstream Zephyr: Zephyr SDK toolchain + `zephyr` workspace + registration. |
| `install custom <name> <git-url> [--rev …] [--toolchain …]` | Any manifest repo — your fork, a private SDK. `--vanilla-toolchain` bases it on a Zephyr SDK instead. |
| `install toolchain <version> [--zephyr-sdk]` | A toolchain on its own. |
| `list [--json]` / `remove <name>` | What is installed (and registered) / delete one. |
| `register [--vscode]` | Rebuild the CMake package registry, and point the extension at the store. |
| `doctor` | Diagnose "SDK not configured" — checks every discovery path. |
| `build` / `shell` / `env <name>` | Headless build / interactive shell / shell exports for one SDK. |
| `flash [--serial …]` | Flash the built `.hex` from **this** machine via `nrfutil device` — see §6. |
| `build-image` | Build the `ncs-base` image and ensure the SDK volume. |

Add `--docker` **before** the subcommand to run any store command in the
container instead of on this filesystem.

### Optional project file

| File | Purpose |
|---|---|
| `.devcontainer/setup-local.sh` *(optional, gitignored)* | If present, the devcontainer runs it on creation — a hook for your own first-time setup (e.g. installing a private/forked SDK). Public copies don't ship one, so it's a no-op. |

---

## 4. Quick practical how-to

### Host requirements & platform support

Works on **Windows 11, Ubuntu/Linux, and macOS** (Intel *and* Apple Silicon). You
need **Docker** and **Python 3** on the host; for host-side flashing you also need
**nrfutil** + **J-Link drivers** on the host.

Invoke the CLI as `./scripts/ncs.py <cmd>` (Linux/macOS, it's executable) or
`python3 scripts/ncs.py <cmd>` / `python scripts\ncs.py <cmd>` (Windows).

| | Build in container | Flash / RTT / VCOM **in** container | Flash from host |
|---|---|---|---|
| **Windows 11** | ✅ | ✅ via `usbipd attach` (§6) | ✅ `ncs.py flash` |
| **Ubuntu/Linux** | ✅ | ✅ **native USB** — no usbipd; `cdc_acm` built in | ✅ |
| **macOS** (Intel/ARM) | ✅ (amd64, emulated on Apple Silicon) | ❌ Docker Desktop has **no USB passthrough** | ✅ — the only hardware path on Mac |

So everyone builds the same way; only the *hardware* path differs. On macOS you
build in the container and **flash/monitor from the host** (`ncs.py flash`, and
JLinkRTTViewer / a serial terminal natively). On Linux it's the smoothest —
the J-Link is a native USB device, so in-container flashing just works once you
rebuild the container. See §6 for the per-OS hardware steps.

### One-time, on this machine

```bash
# 1. Build the small base image (+ create the SDK volume).
#    Optional: the devcontainer builds the image itself from
#    .devcontainer/Dockerfile on first open. Run this if you want the
#    image + volume ready before opening, or for the --docker CLI below.
python scripts/ncs.py build-image

# 2. Install at least one SDK into the shared volume
python scripts/ncs.py --docker install ncs v3.3.0
python scripts/ncs.py --docker install ncs v3.2.4       # as many as you like
python scripts/ncs.py --docker install vanilla v4.2.2   # upstream Zephyr too
```

Prefer to skip Docker and keep the store in WSL under `~/ncs` (no root)? Same
CLI, without `--docker` — see [docs/ncs-cli.md](docs/ncs-cli.md) §2.

### Open the project

VS Code → **Dev Containers: Rebuild and Reopen in Container**. On first creation:

- your SSH **public key** is printed in the creation log
  (View → *Dev Containers: Show Container Log*),
- if a `.devcontainer/setup-local.sh` is present, it runs (your own hook).

Then **nRF Connect → Add build configuration**: pick an **SDK version** and
**toolchain** (e.g. `v3.3.0`), board `nrf5340dk/nrf5340/cpuapp`, and build.

### Build from the integrated terminal

```bash
west build -b nrf5340dk/nrf5340/cpuapp .
```

### Build headless (no VS Code)

```bash
python scripts/ncs.py build                             # default SDK, nRF5340 DK
python scripts/ncs.py build --sdk v3.2.4
python scripts/ncs.py build --sdk my-sdk                # custom SDK, its own toolchain
```

### Switch SDK versions

Just add another build configuration in the extension and pick a different SDK +
toolchain. They sit side-by-side, each with its own build dir. Nothing in the
project pins a version.

### Add a custom / forked / private SDK

```bash
python3 scripts/ncs.py install custom my-sdk git@github.com:me/sdk-nrf-fork.git \
        --rev my-branch --toolchain v3.3.0
```
The toolchain it is based on gets installed first if you don't have it. Use the
git **clone** URL (not the browser `/src/...` URL). After it finishes: **Refresh
SDKs** → it appears as `my-sdk` in *Add build configuration*. For a **private**
repo inside the devcontainer, authorize the container's key first with
`ncs-ssh-setup <host>` (or use the bash equivalent `ncs-add-sdk`, which does the
guided SSH flow itself).

### Optional: a local first-time setup hook

If a file `.devcontainer/setup-local.sh` exists, the devcontainer runs it on
creation (it's gitignored, so it never ships publicly). Use it to automate your
own first-time setup — e.g. installing a private/forked SDK — without touching
the template. Public copies don't include one, so the hook is a no-op.

A self-contained script would, for example, call `ncs-add-sdk` to install a
private SDK fork. To make one run automatically, drop it at
`.devcontainer/setup-local.sh` and rebuild the container.

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
| UART console on `/dev/ttyACM*` | CDC-ACM VCOM | **Yes** — `cdc_acm` in the host kernel (built in on Linux; a module on WSL2) |

So **flashing and RTT monitoring work in the container** (Windows/Linux); the VCOM
serial port additionally needs `cdc_acm` — already present on Linux and on recent
WSL2 kernels. **RTT replaces it**, so the serial port is optional.

### In the container — Linux host (simplest)

The J-Link is a native USB device, so there's **no usbipd** and `cdc_acm` is in
the stock kernel. Just rebuild the container and flash:
```bash
west flash -d build          # in the container terminal
```
RTT and the `/dev/ttyACM*` VCOM both work out of the box (the devcontainer already
has `--privileged` + the `/dev` mount + the J-Link runtime). If your host user
isn't in the `docker`/`dialout` groups you may need to add it for probe access.

### In the container — Windows host (WSL2 + usbipd)

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
| `.devcontainer/Dockerfile` | Builds `ncs-base` (host tools + nrfutil + the `ncs-*` helper commands). |
| `.devcontainer/.dockerignore` | Keeps the image build context empty (no SDK, no source). |
| `.devcontainer/devcontainer.json` | `build` block (points at the Dockerfile beside it), volume mounts, workspace bind, extension list, the `installDirectory` setting, `postCreate`/`postStart` commands. |
| `.devcontainer/setup-local.sh` | *(optional, gitignored)* your own first-time setup hook — absent in public copies. |
| `CMakeLists.txt`, `prj.conf`, `src/main.cpp` | The freestanding C++23 app. |
| `sample.yaml` | Twister build test (`west twister -T .`). |
| `debug-overlay.conf` | Extra debug Kconfig (`-DEXTRA_CONF_FILE=...`). |
| `scripts/ncs.py` | The one CLI: install/register/list/build/shell/flash (see §3). |
| `docs/ncs-cli.md` | Full guide to that CLI: the store, moving it, adding each kind of SDK, registration, troubleshooting. |
| `.clang-format`, `.clang-tidy`, `.cmake-format.yaml`, `.vscode/settings.json` | Formatting/lint/IntelliSense config. |
| `.gitattributes` | Forces `*.sh` to LF (they run in Linux). |

---

## 8. Starting a new project from this template

1. Copy the whole folder to a new name.
2. (Optional) rename `project()` in `CMakeLists.txt`.
3. (Optional) for private/internal setup, drop a `.devcontainer/setup-local.sh`
   (gitignored) — see "Optional: a local first-time setup hook" in §4.
4. **Reopen in Container.** It builds/reuses the same `ncs-base` image and mounts
   the same `ncs-sdks` volume — no SDK re-download. Pick an SDK in the extension
   and build.

### Reusing just the devcontainer in an existing Zephyr project

`.devcontainer/` is self-contained: it holds both `devcontainer.json` **and** the
`Dockerfile` it builds, and nothing in it reads from the project tree. So you can

```bash
cp -r .devcontainer /path/to/other-zephyr-project/
```

and **Reopen in Container** there. On the *same machine* the `ncs-sdks` volume
already holds your SDKs, so they show up immediately (Docker's layer cache also
makes the image build near-instant). On a *new machine*, install an SDK once —
`ncs-add-sdk` in the container terminal, the extension's **Manage SDKs**, or
`python scripts/ncs.py --docker install ncs v3.3.0` from this template — and
every project after that gets it for free.
