# CLAUDE.md

Template for Zephyr and nRF Connect SDK C++23 applications, developed in a devcontainer
with the SDKs in a shared Docker volume (`ncs-sdks` at `/root/ncs`). The app is
freestanding: there is no `west.yml`, it builds against whichever SDK `ZEPHYR_BASE` or
the CMake package registry points at.

## The one rule that matters

**Never ship Zephyr code you have not built.** Kconfig, devicetree and the Twister
harness only show up in a real build. Work happens on Windows and the toolchain lives in
the Linux devcontainer, so find it and run there:

```bash
docker ps --format '{{.ID}}\t{{.Image}}'
```

```bash
docker exec <id> bash -lc 'cd /workspaces/zephyr-cpp-template && west twister -T . -p native_sim -p nrf5340dk/nrf5340/cpuapp -O /tmp/tw --clobber-output'
```

Always pass `-O /tmp/<name> --clobber-output`. Twister rotates `twister-out/` on every
run, and that rotation fails on the Windows bind mount with
`OSError: [Errno 39] Directory not empty`.

## Layout

| | |
|---|---|
| `src/`, `CMakeLists.txt`, `prj.conf` | the app. `prj.conf` stays board-neutral. |
| `boards/` | per-board `.conf` and `.overlay`, merged in by board name |
| `sample.yaml` | Twister scenarios, named `template.<domain>.<kind>` |
| `scripts/ncs.py` | the SDK CLI: install, register, doctor, build, flash. Guide in `docs/ncs-cli.md`. |
| `.devcontainer/` | self-contained: `devcontainer.json` plus the `Dockerfile` it builds |
| `.github/workflows/ci.yml` | format check, then Twister in `zephyr-devcontainer-ci` |
| `docs/` | indexed in `docs/README.md` |

## House style

- No em dashes anywhere, in code comments, docs or commit messages.
- No company, customer or private repository names. This repo is public and agnostic;
  private setup lives in the gitignored `private/` and `.devcontainer/setup-local.sh`.
- C and C++ are 4 spaces, no tabs, 100 columns (`.editorconfig`, `.clang-format`).
- Comments state the decision and its reason in one or two lines. No investigation
  history, no narration, no comments that only restate the code.
