# `scripts/ncs.py` — one CLI for SDKs, toolchains and registration

One Python file manages every Zephyr SDK you use: official **nRF Connect SDK**,
**vanilla Zephyr**, and your own **custom / forked / private** SDKs — plus their
toolchains — and registers all of them so the *nRF Connect for VS Code*
extension lists them.

It runs the same way in three places:

| Where | Store lives in | How |
|---|---|---|
| **WSL / Linux / macOS, native** | `~/ncs` (or anywhere you point it) | default — no root needed |
| **Inside the devcontainer** | `$NCS_INSTALL_DIR` (`/root/ncs` by default) | default — the env var is picked up automatically |
| **From a Windows/macOS host** | the `ncs-sdks` Docker volume | add `--docker` before the subcommand |

```
python3 scripts/ncs.py --help          # every command
python3 scripts/ncs.py <cmd> --help    # one command
```

---

## 1. The store

Everything lives in one directory — the **store** — with a layout the extension
understands natively:

```
<store>/                       default ~/ncs, changeable (§3)
├── toolchains/
│   ├── toolchains.json        nrfutil's index of NCS toolchain bundles
│   ├── 911f4c5c26/            an NCS toolchain bundle (gcc, cmake, west, python)
│   └── zephyr-sdk-0.17.0/     an upstream Zephyr SDK (the "vanilla" toolchain)
├── v3.3.0/                    official NCS west workspace
├── zephyr-v4.2.2/             vanilla Zephyr west workspace
├── my-sdk/                    your fork — any folder name works
└── .venv/                     west + python deps for vanilla work
```

Each SDK folder also gets a small `.ncs-sdk.json` written by this tool, recording
which toolchain it belongs to. That is what lets `build`, `shell` and `env` pick
the right toolchain without you naming it every time.

Nothing in a *project* pins an SDK: the SDK you pick per build configuration (or
via `--sdk`) decides. So many projects share one store.

---

## 2. First-time setup

### Native (WSL, Linux, macOS) — no root, no `/root/ncs`

```bash
python3 scripts/ncs.py bootstrap                      # nrfutil -> ~/.local/bin
python3 scripts/ncs.py config set install-dir ~/ncs   # the store
python3 scripts/ncs.py install ncs v3.3.0             # SDK + matching toolchain
python3 scripts/ncs.py register --vscode              # make the extension see it
python3 scripts/ncs.py doctor                         # verify
```

`bootstrap` downloads `nrfutil` for your OS/arch into `~/.local/bin` and installs
its `toolchain-manager`, `sdk-manager` and `device` sub-commands. Everything from
there on is per-user — nothing is written outside your home directory and the
store. If `~/.local/bin` is not on your `PATH` yet, `bootstrap` prints the line to
add.

Host packages you still need in WSL: `git`, `curl` or `wget` (the Zephyr SDK's
`setup.sh` uses them), `python3-venv`, and `xz-utils` or `tar`.

### From a Windows/macOS host, using Docker

```bash
python scripts\ncs.py build-image                     # ncs-base image + volume
python scripts\ncs.py --docker install ncs v3.3.0
python scripts\ncs.py --docker list
```

`--docker` re-runs *this same script* inside the `ncs-base` container with the
`ncs-sdks` volume mounted, so there is exactly one implementation of every
command. It must come **before** the subcommand.

> Registration is the one thing the docker backend cannot finish for you: the
> CMake registry lives in `~/.cmake` inside the container, so it has to be
> written in the container VS Code actually attaches to. The devcontainer does
> that on every start (see §4).

---

## 3. Moving the store (e.g. to `~/ncs` in WSL)

The store directory is resolved in this order — first hit wins:

1. `--install-dir <path>` on the command line
2. `$NCS_INSTALL_DIR` in the environment
3. the config file (`~/.config/ncs-tool/config.json`, `%APPDATA%\ncs-tool\` on Windows)
4. `~/ncs`

```bash
python3 scripts/ncs.py config set install-dir ~/ncs   # persistent
python3 scripts/ncs.py config show                    # what is in effect
python3 scripts/ncs.py config unset install-dir       # back to the default
NCS_INSTALL_DIR=/mnt/big/ncs python3 scripts/ncs.py list   # one-off
```

`config set install-dir` also re-points **nrfutil's own** install dirs
(`toolchain-manager` and `sdk-manager` keep their own), so installs and lookups
agree. It then reminds you about the VS Code setting, which is a *third*
independent place — write it with `register --vscode`.

### If you move the devcontainer's store off `/root/ncs`

The container has three hard-coded references. Change all three together:

| File | What to change |
|---|---|
| [Dockerfile](../Dockerfile) | `ENV NCS_INSTALL_DIR=/root/ncs` |
| [.devcontainer/devcontainer.json](../.devcontainer/devcontainer.json) | the mount `source=ncs-sdks,target=/root/ncs` |
| [.devcontainer/devcontainer.json](../.devcontainer/devcontainer.json) | the setting `nrf-connect.toolchainManager.installDirectory` |

The container path must be the **home directory of the container user**'s `ncs`
folder, because that is where the extension installs by default. So if you also
switch `remoteUser` away from `root`, use `/home/<user>/ncs` in all three.
`ncs.py` itself needs no edit — it reads `NCS_INSTALL_DIR`.

Not using the devcontainer at all (native WSL + the VS Code WSL extension) is
simpler: one `config set install-dir ~/ncs` plus `register --vscode`.

---

## 4. How the extension finds things — and how this tool guarantees it

The nRF Connect extension discovers **toolchains** and **SDKs** through two
completely separate mechanisms. Both must point at your store:

| What | How the extension finds it | What satisfies it |
|---|---|---|
| **Toolchains** | runs `nrfutil` with an `--install-dir` taken from the setting `nrf-connect.toolchainManager.installDirectory` | `ncs.py register --vscode` (writes `.vscode/settings.json`), or the setting in `devcontainer.json` |
| **SDKs** | reads the **CMake user package registry** `~/.cmake/packages/Zephyr` — where `west zephyr-export` registers a Zephyr tree | `ncs.py register` — every install ends with it |

`register` walks the store and registers **every** west workspace it finds. The
test is structural, not name-based: a folder counts as an SDK if it contains
`zephyr/share/zephyr-package/cmake`. That is why a custom SDK with any folder
name shows up just like an official one. It also registers `ZephyrUnittest` and
any `zephyr-sdk-*` toolchain (as `Zephyr-sdk`), and prunes entries whose
directory is gone.

```bash
python3 scripts/ncs.py register            # registry only
python3 scripts/ncs.py register --vscode   # + the extension's install dir
```

`register --vscode` edits `.vscode/settings.json` as *text*, so the comments in it
survive (VS Code settings are JSONC, which `json.dump` would destroy). It updates
the value in place if the key is already there, otherwise inserts it at the top,
matching the file's own indentation — and leaves a `settings.json.bak` behind.

After registering: **nRF Connect: Refresh SDKs**, or reload the window.

In the devcontainer this runs automatically on every start (`postStartCommand`),
because `~/.cmake` lives in the container's writable layer and is lost on
rebuild. The image also ships a bash equivalent, `ncs-register-sdks`.

### When the extension still says "SDK not configured"

```bash
python3 scripts/ncs.py doctor
```

It checks, and tells you which one is wrong: the store exists · `nrfutil` is on
`PATH` · nrfutil's install-dir matches the store · every SDK is in the CMake
registry · no stale registry entries · the VS Code setting matches · at least one
toolchain is installed. Exit code is non-zero if anything failed.

---

## 5. Adding SDKs

### Official nRF Connect SDK

```bash
python3 scripts/ncs.py install ncs v3.3.0
python3 scripts/ncs.py install ncs v2.4.0 --shallow    # smaller clone
```

Installs the matching **nrfutil toolchain bundle** if missing, then fetches the
`sdk-nrf` manifest with that bundle's own `west` into `<store>/v3.3.0`, and
registers it. Add `--blobs` if you need `hal_nordic` binary blobs (nRF70 Wi-Fi
and friends).

### Vanilla Zephyr

```bash
python3 scripts/ncs.py install vanilla v4.2.2
python3 scripts/ncs.py install vanilla v4.2.2 --zephyr-sdk-version 0.17.0 \
        --target arm-zephyr-eabi --target x86_64-zephyr-elf
```

Downloads the **Zephyr SDK** (`sdk-ng` minimal bundle for your host) into
`<store>/toolchains/zephyr-sdk-<ver>` and runs its `setup.sh -h -c -t …`, then
fetches upstream Zephyr into `<store>/zephyr-v4.2.2` using a store-local venv's
`west`, and installs `zephyr/scripts/requirements.txt` into that venv
(`--no-python-deps` to skip). Default targets are `arm-zephyr-eabi` and
`x86_64-zephyr-elf` — the second one is what `native_sim` needs.

Vanilla workspaces register in the CMake registry exactly like NCS ones, so the
extension lists them as SDKs. Their toolchain is a Zephyr SDK rather than an
nrfutil bundle, so if the extension's toolchain dropdown does not offer it, build
those from the CLI (`ncs.py build --sdk zephyr-v4.2.2`) — everything else, including
IntelliSense from `compile_commands.json`, works the same.

### A custom / forked / private SDK

```bash
# public fork
python3 scripts/ncs.py install custom my-sdk https://github.com/me/sdk-nrf.git \
        --rev my-branch --toolchain v3.3.0

# private repo over SSH (uses your normal key/agent in WSL)
python3 scripts/ncs.py install custom private-sdk git@github.com:me/private-sdk-nrf.git \
        --rev main --toolchain v3.1.1

# a fork based on upstream Zephyr rather than NCS
python3 scripts/ncs.py install custom my-zephyr https://github.com/me/zephyr.git \
        --rev main --vanilla-toolchain 0.17.0
```

`name` is the folder in the store and the name the extension shows. `--toolchain`
is the **NCS toolchain version** the SDK is built with; it is installed first if
missing. Use the git **clone** URL, not a browser `/src/…` URL. Extra knobs:
`--manifest-file` (manifest other than `west.yml`), `--shallow`, `--blobs`,
`--reuse` (continue into a folder that already exists).

In the **devcontainer**, an SSH URL needs the container's key authorized first:

```bash
ncs-ssh-setup bitbucket.org      # ensure key -> open the host's key page -> verify
python3 scripts/ncs.py install custom private-sdk git@github.com:me/private-sdk-nrf.git \
        --rev main --toolchain v3.1.1
```

### A toolchain on its own

```bash
python3 scripts/ncs.py install toolchain v3.1.1              # nrfutil NCS bundle
python3 scripts/ncs.py install toolchain 0.17.0 --zephyr-sdk # Zephyr SDK
```

---

## 6. Using what you installed

```bash
python3 scripts/ncs.py list                  # SDKs, toolchains, registration state
python3 scripts/ncs.py list --json           # same, for scripts

python3 scripts/ncs.py build                                  # default SDK + board
python3 scripts/ncs.py build --sdk private-sdk --board nrf5340dk/nrf5340/cpuapp
python3 scripts/ncs.py build --sdk zephyr-v4.2.2 --board native_sim --pristine
python3 scripts/ncs.py build -- -DEXTRA_CONF_FILE=debug-overlay.conf

python3 scripts/ncs.py shell --sdk v3.3.0    # interactive, SDK env applied
eval "$(python3 scripts/ncs.py env v3.3.0)"  # or apply it to THIS shell

python3 scripts/ncs.py remove old-sdk        # delete + prune registration
python3 scripts/ncs.py flash --serial 1050073602
```

`build` picks the SDK from `--sdk`, else the `toolchain` config value if a folder
of that name exists, else the only installed SDK — and refuses to guess when
several are installed. `env` prints POSIX-shell exports (`ZEPHYR_BASE`,
`ZEPHYR_SDK_INSTALL_DIR`, `PATH`, …) for the SDK you name, which is the handy way
to make an ordinary terminal, `west`, `twister` or a CI step use one specific SDK.

`flash` always runs on the machine you invoke it from (never in the container) —
see the hardware notes in [README §6](../README.md).

---

## 7. Command reference

| Command | What it does |
|---|---|
| `bootstrap` | Download `nrfutil` into `~/.local/bin` (`--bin-dir` to change) and install its sub-commands. No root. |
| `config show` \| `set <key> <value>` \| `unset <key>` | Read/write the persistent settings. Keys: `install-dir`, `backend`, `toolchain`, `board`, `zephyr-sdk-version`, `image`, `volume`, `container-install-dir`. |
| `install ncs [version]` | Official NCS: toolchain + `sdk-nrf` workspace + registration. |
| `install vanilla [version]` | Upstream Zephyr: Zephyr SDK + `zephyr` workspace + registration. |
| `install custom <name> <git-url>` | Any manifest repo, with an NCS toolchain (`--toolchain`) or a Zephyr SDK (`--vanilla-toolchain`). |
| `install toolchain <version>` | A toolchain only. `--zephyr-sdk` for the vanilla kind. |
| `list [--json]` | Every SDK and toolchain in the store, and whether it is registered. |
| `register [--vscode]` | Rebuild the CMake package registry; optionally write the extension's install-dir setting. |
| `remove <name> [-y]` | Delete an SDK folder and prune its registration. |
| `env <name>` | Print shell exports for one SDK: `eval "$(… env <name>)"`. |
| `doctor` | Diagnose why the extension cannot see an SDK or toolchain. |
| `build` | Headless `west build` with a chosen SDK. `--sdk --board --source --build-dir --pristine`, then extra `west build` args. |
| `shell` | Interactive shell with one SDK's environment. |
| `flash` | Flash a built `.hex` from this machine via `nrfutil device` (J-Link). |
| `build-image` | Build the `ncs-base` image and ensure the `ncs-sdks` volume (docker backend). |

Global flags, always **before** the subcommand: `--install-dir <path>`,
`--backend local|docker`, `--docker`.

---

## 8. Notes and limits

- **Windows natively** works for `flash`, `config`, `bootstrap` and the `--docker`
  backend. Installing SDKs on the Windows filesystem is not supported here — the
  Zephyr SDK setup and the CMake registry are POSIX-shaped. Use WSL or `--docker`.
- **The CMake registry is per user and per machine.** A store shared over a mount
  still needs `register` run once per user/container that should see it.
- **`west zephyr-export` is best-effort** during installs (it needs `cmake` on
  `PATH`); `register` does the same job unconditionally, so an install never fails
  over it.
- **Space**: a full NCS workspace is several GB. `--shallow` (`west update
  --narrow --depth 1`) cuts that a lot; skip it if you need full history for
  bisecting or branching inside the SDK.
