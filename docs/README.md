# Documentation

| | |
|---|---|
| [`setup/devcontainer.md`](setup/devcontainer.md) | how the image, the SDK volume and the project fit together, how the nRF Connect extension finds SDKs, and the commands baked into the image |
| [`setup/flash-monitor.md`](setup/flash-monitor.md) | flashing and reading logs (RTT or UART VCOM) from the container or the host, per OS |
| [`ncs-cli.md`](ncs-cli.md) | the full guide to `scripts/ncs.py`: the store, moving it, adding each kind of SDK, registration, troubleshooting |
| [`notes/`](notes/) | working notes, not written for a reader |

Start with `setup/devcontainer.md` if the extension says **"SDK not configured"**, or
run `python3 scripts/ncs.py doctor`.
