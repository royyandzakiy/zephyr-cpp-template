# The devcontainer and the SDK store

How the container is put together, how the nRF Connect extension finds SDKs inside it,
and what the helper commands baked into the image do. For installing SDKs, see
[`../ncs-cli.md`](../ncs-cli.md).

## 1. How it is put together

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
│  CMakeLists.txt  prj.conf  src/main.cpp  │   src, NOT inside the SDK tree.
└──────────────────────────────────────────┘
```

Why this shape:

- **Image stays tiny**, it has *no* SDK, so it rarely changes and copies instantly.
- **SDKs are a volume, not image layers**, installed once with `nrfutil`/`west`,
  reused by every container and project, and you add/remove versions with **no
  image rebuild**.
- **Projects are freestanding**, nothing in a project pins an SDK version; the
  build configuration you pick in the extension decides. That's what makes
  switching versions clean.

---

## 2. How the extension finds SDKs

The nRF Connect extension discovers toolchains and SDKs through **two separate
mechanisms**, and both have to point at the same **store** directory (the volume
target `/root/ncs` in the container, or e.g. `~/ncs` natively in WSL).


| What | How the extension finds it | What makes it work here |
|---|---|---|
| **Toolchains** | runs `nrfutil toolchain list --install-dir <dir>` | the setting **`nrf-connect.toolchainManager.installDirectory` = the store**, in `devcontainer.json`, or written by `ncs.py register --vscode` |
| **SDKs** | reads the **CMake user package registry** `~/.cmake/packages/Zephyr` (where `west zephyr-export` registers Zephyr) | **`ncs.py register`**, run by every install, and on every container start via `postStartCommand` |

So if the extension ever says **"SDK not configured"** or a version is missing,
run `python3 scripts/ncs.py doctor`, it checks both mechanisms and reports which
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
| Where the store is, natively | `python3 scripts/ncs.py config set install-dir ~/ncs`, see [`../ncs-cli.md`](../ncs-cli.md) §3 |
| Where the store is, in the container | `nrf-connect.toolchainManager.installDirectory` in [.devcontainer/devcontainer.json](../../.devcontainer/devcontainer.json), the volume mount target there, and `NCS_INSTALL_DIR` in the [.devcontainer/Dockerfile](../../.devcontainer/Dockerfile), all three together |
| When SDKs get registered | `postStartCommand` in [.devcontainer/devcontainer.json](../../.devcontainer/devcontainer.json) |
| *Which* folders count as SDKs | `scripts/ncs.py register` (and the baked-in `ncs-register-sdks`), any folder in the store containing `zephyr/share/zephyr-package/cmake`, whatever its name |

## 3. Commands baked into the image

On `PATH` in every container:

| Command | Purpose |
|---|---|
| `ncs-register-sdks` | Registers **every** west workspace in `/root/ncs` (official + custom, any folder name) into the CMake package registry so the extension lists them. Run automatically by `postStartCommand`. |
| `ncs-ssh-key [--new]` | Ensures an SSH key exists and prints the **public** key. Reuses the existing key (persisted in the `ncs-ssh` volume); `--new` forces a fresh one. Run by `postCreateCommand`. |
| `ncs-ssh-setup <host>` | **Guided** SSH authorization: ensure key → open the host's SSH-keys page in your browser → wait while you add it → verify `ssh -T`. Hosts: `bitbucket.org`, `github.com`, `gitlab.com`. |
| `ncs-add-sdk <custom-folder-name> <git-url> [branch] [toolchain] [manifest-file]` | Installs any custom SDK from a git manifest repo into the volume and registers it. For an SSH URL it runs `ncs-ssh-setup` first. Run it in the devcontainer terminal. |


`scripts/ncs.py` is covered in [`../ncs-cli.md`](../ncs-cli.md).

## 4. Optional: a local first-time setup hook

If a file `.devcontainer/setup-local.sh` exists, the devcontainer runs it on
creation (it's gitignored, so it never ships publicly). Use it to automate your
own first-time setup, e.g. installing a private/forked SDK, without touching
the template. Public copies don't include one, so the hook is a no-op.

A self-contained script would, for example, call `ncs-add-sdk` to install a
private SDK fork. To make one run automatically, drop it at
`.devcontainer/setup-local.sh` and rebuild the container.

## 5. Reusing just the devcontainer in another Zephyr project

`.devcontainer/` is self-contained: it holds both `devcontainer.json` **and** the
`Dockerfile` it builds, and nothing in it reads from the project tree. So you can

```bash
cp -r .devcontainer /path/to/other-zephyr-project/
```

and **Reopen in Container** there. On the *same machine* the `ncs-sdks` volume
already holds your SDKs, so they show up immediately (Docker's layer cache also
makes the image build near-instant). On a *new machine*, install an SDK once  - 
`ncs-add-sdk` in the container terminal, the extension's **Manage SDKs**, or
`python scripts/ncs.py --docker install ncs v3.3.0` from this template, and
every project after that gets it for free.
