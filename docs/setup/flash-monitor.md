# Flashing and monitoring

Getting the image onto a board, from inside the devcontainer or from the host, and
reading its logs over RTT or the UART VCOM.

Two interfaces matter on the J-Link, and they have very different needs:

| Task | Interface | Needs a kernel driver? |
|---|---|---|
| Flash, debug, **RTT monitor** | debug probe, via **libusb** | No, just USB access (`--privileged`) |
| UART console on `/dev/ttyACM*` | CDC-ACM VCOM | **Yes**, `cdc_acm` in the host kernel (built in on Linux; a module on WSL2) |

So **flashing and RTT monitoring work in the container** (Windows/Linux); the VCOM
serial port additionally needs `cdc_acm`, already present on Linux and on recent
WSL2 kernels. **RTT replaces it**, so the serial port is optional.

## In the container, Linux host (simplest)

The J-Link is a native USB device, so there's **no usbipd** and `cdc_acm` is in
the stock kernel. Just rebuild the container and flash:
```bash
west flash -d build          # in the container terminal
```
RTT and the `/dev/ttyACM*` VCOM both work out of the box (the devcontainer already
has `--privileged` + the `/dev` mount + the J-Link runtime). If your host user
isn't in the `docker`/`dialout` groups you may need to add it for probe access.

## In the container, Windows host (WSL2 + usbipd)

1. Forward the probe to WSL2 (this detaches it from Windows):
   ```powershell
   usbipd list                          # find the J-Link BUSID
   usbipd attach --wsl --busid <BUSID>
   ```
2. The devcontainer has `--privileged` + a whole-`/dev` bind (see
   `devcontainer.json` §`runArgs`/`mounts`), and the image bundles the **SEGGER
   J-Link runtime** (`libjlinkarm`) that `nrfutil device` needs, so the probe is
   both reachable *and* drivable. (Without that runtime you'd see "JLinkARM DLL
   not found" / "device cannot be recognized (NotFound)".)
3. **Flash**: the extension's Flash action, or in the terminal:
   ```bash
   west flash -d build
   ```
4. **Monitor, RTT (simplest)**: *nRF Connect: Connect to RTT* (or the RTT button
   on the build). RTT goes over the debug probe, so it needs nothing else.

### Monitor over the UART VCOM (`/dev/ttyACM*`) instead of RTT

Only needed if you want the actual UART console (MCUboot serial recovery, a UART
shell, or firmware that logs only to UART). It needs the `cdc_acm` kernel module  - 
recent WSL2 kernels ship it. One-time per WSL session, **before** attaching:

```powershell
wsl -d <your-distro> -- sudo modprobe cdc_acm   # load it (kernel-global)
usbipd attach --wsl --busid <BUSID>             # node /dev/ttyACM* now appears
```
The whole-`/dev` mount means the container sees `/dev/ttyACM*` automatically. Open
it in the nRF Connect serial terminal (the nRF5340 DK app-core console is usually
**VCOM1 / `/dev/ttyACM1`**) at 115200, or `screen /dev/ttyACM1 115200`.

> If `modprobe cdc_acm` reports the module isn't found, your WSL2 kernel lacks it  - 
> run `wsl --update`, or build a custom kernel with `CONFIG_USB_ACM=y` and point
> `.wslconfig`'s `kernel=` at it. (You do **not** need to reinstall your distro  - 
> the kernel is shared across all WSL2 distros + Docker, independent of any distro.)

## From the host (fallback / simplest)

If you'd rather not juggle `usbipd` (you can't use the probe on Windows and in
WSL at the same time), build in the container and flash from the host:

```bash
python scripts/ncs.py flash                       # picks build/merged.hex
python scripts/ncs.py flash --serial 1050073602   # if more than one probe
```
That runs the host's `nrfutil device program` against the `.hex` in the
bind-mounted `build/` folder (needs `nrfutil` + J-Link drivers on the host). For
the UART console, open the J-Link VCOM port in a serial terminal.
