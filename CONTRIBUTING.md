# Contributing

For anyone proposing a change to this template: a fix to the app, the devcontainer,
`scripts/ncs.py`, or the docs.

## Getting an environment

Docker is the only prerequisite. Open the repo in VS Code and accept *"Reopen in
Container"*, then install an SDK once, see the [README](README.md#quick-start).

## Before you open a pull request

1. **Build it.** Kconfig, devicetree and the Twister harness only show up in a real
   build, so run the same command CI runs:

   ```bash
   west twister -T . -p native_sim -p nrf5340dk/nrf5340/cpuapp -O /tmp/tw --clobber-output
   ```

2. **Format it.** `git ls-files '*.c' '*.h' '*.cpp' '*.hpp' | xargs clang-format -i`
3. **If you changed `scripts/ncs.py`**, run the commands you touched against a real store,
   and `python3 scripts/ncs.py doctor` afterwards.
4. **Report the numbers from the run**, not an impression of it. Paste the Twister
   summary line.

## Code style

C and C++ are 4 spaces, no tabs, 100 columns, recorded in [`.editorconfig`](.editorconfig)
and [`.clang-format`](.clang-format). That differs from Zephyr upstream, which uses tabs,
and is deliberate.

Keep `prj.conf` board-neutral. Anything that only exists on some boards (RTT, a
specific driver, a pin) goes in `boards/<board>.conf` or `boards/<board>.overlay`, so
the app still builds on native_sim.

Comments state the decision and its reason in one or two lines: what a line or setting
does, and what it is required for. No investigation history, no narration, no comments
that only restate the code. Where a line exists to avoid a specific bug, say what the
tempting wrong version does and what it costs.

## Writing docs

- **No em dashes**, anywhere, in code comments, docs or commit messages. Use a comma, a
  spaced hyphen, parentheses, or two sentences.
- **One owner per fact.** The README owns the quick start. `docs/` owns how each piece
  works in detail. Where they would overlap, the README links.
- **Keep it agnostic.** The template names no company, customer or private repository.
  Examples use placeholders such as `my-sdk` and `git@github.com:me/sdk-nrf-fork.git`.
  Private setup goes in a gitignored `.devcontainer/setup-local.sh` or `private/`.
