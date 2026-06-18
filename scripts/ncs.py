#!/usr/bin/env python3
"""
Cross-platform (Linux / macOS / Windows) helper CLI for this nRF Connect SDK
dev-container template. Replaces the old per-task PowerShell scripts.

  python scripts/ncs.py --help
  python scripts/ncs.py build-image
  python scripts/ncs.py install-sdk v3.3.0
  python scripts/ncs.py install-custom-sdk my-sdk git@github.com:me/sdk-nrf.git --rev main
  python scripts/ncs.py build  --sdk private-sdk --ncs v3.1.1
  python scripts/ncs.py shell  --ncs v3.3.0
  python scripts/ncs.py flash  --serial 1050073602

Only HOST-side orchestration lives here; the in-container helpers
(ncs-register-sdks, ncs-ssh-setup, ncs-add-sdk) stay as bash, baked in the image.
"""
import argparse
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]   # project root (scripts/ is under it)
PROJECT = ROOT.name
DEST = f"/workspaces/{PROJECT}"               # where the project mounts in-container
IMAGE = "ncs-base:latest"
VOLUME = "ncs-sdks"
NCS_DIR = "/root/ncs"
PLATFORM = "linux/amd64"   # x86_64 tooling; emulated on Apple Silicon / arm64


def run(cmd, **kw):
    """Run a command (list form — no shell), echoing it first."""
    print("+ " + " ".join(shlex.quote(c) for c in cmd))
    return subprocess.run(cmd, check=True, **kw)


def docker_run(args, *, interactive=False, with_project=False):
    """Assemble a `docker run` invocation against the shared SDK volume."""
    cmd = ["docker", "run", "--rm", "--platform", PLATFORM]
    if interactive:
        tty = sys.stdin.isatty() and sys.stdout.isatty()
        cmd += ["-it"] if tty else ["-i"]
    cmd += ["-v", f"{VOLUME}:{NCS_DIR}"]
    if with_project:
        cmd += ["-v", f"{ROOT}:{DEST}"]
    cmd += [IMAGE] + args
    return run(cmd)


def launch(ncs_rev, inner):
    """Args that run `inner` (one bash -c string) inside a toolchain env.

    Passed as a clean argv list — no nested shell quoting needed.
    """
    return ["nrfutil", "toolchain-manager", "launch",
            "--ncs-version", ncs_rev, "--", "bash", "-c", inner]


# --- subcommands -------------------------------------------------------------

def cmd_build_image(a):
    run(["docker", "build", "--platform", PLATFORM, "-t", IMAGE, str(ROOT)])
    run(["docker", "volume", "create", VOLUME], stdout=subprocess.DEVNULL)
    print(f"\nBuilt {IMAGE} and ensured volume '{VOLUME}'.")
    print("Next: install an SDK  ->  python scripts/ncs.py install-sdk v3.3.0")


def cmd_install_sdk(a):
    if a.list:
        docker_run(["bash", "-lc",
                    "echo '=== available ==='; nrfutil sdk-manager search; "
                    "echo; echo '=== installed ==='; nrfutil sdk-manager list"])
        return
    docker_run(["bash", "-lc",
                f"nrfutil sdk-manager install {shlex.quote(a.ncs_rev)} --install-dir {NCS_DIR}"])
    print(f"\nInstalled NCS {a.ncs_rev} into volume '{VOLUME}'.")


def cmd_install_custom_sdk(a):
    dest = f"{NCS_DIR}/{a.name}"
    init = f"west init -m {shlex.quote(a.url)}"
    if a.rev:
        init += f" --mr {shlex.quote(a.rev)}"
    if a.manifest_file:
        init += f" --mf {shlex.quote(a.manifest_file)}"
    init += f" {shlex.quote(dest)}"

    steps = [init, f"cd {shlex.quote(dest)}", "west update"]
    if a.blobs:
        steps.append("west blobs fetch hal_nordic || true")
    steps.append("west zephyr-export")
    inner = " && ".join(steps)

    print(f"Installing custom SDK '{a.name}' from {a.url} (toolchain env: {a.toolchain})...")
    docker_run(launch(a.toolchain, inner))
    print(f"\nInstalled custom SDK '{a.name}' into '{VOLUME}' at {dest}.")
    print(f"In the extension: Add build configuration -> SDK = '{a.name}', Toolchain = {a.toolchain}.")
    print(f"Headless build:   python scripts/ncs.py build --sdk {a.name} --ncs {a.toolchain}")


def cmd_build(a):
    sdk = a.sdk or a.ncs                 # default: SDK folder == toolchain version
    pristine = " -p always" if a.pristine else ""
    inner = (f"export ZEPHYR_BASE={NCS_DIR}/{sdk}/zephyr; "
             f"west build -b {a.board} {DEST} --build-dir {DEST}/build{pristine}")
    docker_run(launch(a.ncs, inner), with_project=True)
    print(f"\nBuilt {PROJECT} for {a.board} (SDK={sdk}, toolchain={a.ncs}).")
    print(f"Flash:  python scripts/ncs.py flash")


def cmd_shell(a):
    sdk = a.sdk or a.ncs
    inner = f"export ZEPHYR_BASE={NCS_DIR}/{sdk}/zephyr; cd {DEST}; exec bash"
    docker_run(launch(a.ncs, inner), interactive=True, with_project=True)


def cmd_flash(a):
    # Host-side flash via nrfutil device (J-Link). Build in the container first.
    nrfutil = a.nrfutil or shutil.which("nrfutil")
    if not nrfutil and sys.platform == "win32":
        cand = Path(r"C:\ncs\nrfutil.exe")
        if cand.exists():
            nrfutil = str(cand)
    if not nrfutil:
        sys.exit("nrfutil not found on PATH. Install it, or pass --nrfutil <path>.")

    hexfile = a.hex
    if not hexfile:
        merged = ROOT / "build" / "merged.hex"
        if merged.exists():
            hexfile = str(merged)
        else:
            found = next((ROOT / "build").rglob("zephyr.hex"), None)
            hexfile = str(found) if found else None
    if not hexfile or not Path(hexfile).exists():
        sys.exit("No .hex under build/. Build in the container first, then flash on the host.")

    print(f"Flashing {hexfile} (core: {a.core})")
    cmd = [nrfutil, "device", "program", "--firmware", hexfile, "--core", a.core,
           "--options", "chip_erase_mode=ERASE_RANGES_TOUCHED_BY_FIRMWARE,reset=RESET_SYSTEM"]
    if a.serial:
        cmd += ["--serial-number", a.serial]
    run(cmd)
    print("Done.")


# --- arg parsing -------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(prog="ncs.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("build-image", help="Build the ncs-base image + ensure the SDK volume")
    sp.set_defaults(func=cmd_build_image)

    sp = sub.add_parser("install-sdk", help="Install an official NCS version into the volume")
    sp.add_argument("ncs_rev", nargs="?", default="v3.3.0", help="e.g. v3.3.0 (default)")
    sp.add_argument("--list", action="store_true", help="List available/installed instead")
    sp.set_defaults(func=cmd_install_sdk)

    sp = sub.add_parser("install-custom-sdk", help="Install a custom SDK from any git manifest")
    sp.add_argument("name", help="Folder name under the volume, e.g. my-sdk")
    sp.add_argument("url", help="git CLONE url (not the browser /src/ url)")
    sp.add_argument("--rev", default="", help="branch/tag/commit (manifest revision)")
    sp.add_argument("--manifest-file", default="", help="manifest file if not west.yml")
    sp.add_argument("--toolchain", default="v3.3.0", help="installed toolchain to build with")
    sp.add_argument("--blobs", action="store_true", help="also `west blobs fetch hal_nordic`")
    sp.set_defaults(func=cmd_install_custom_sdk)

    sp = sub.add_parser("build", help="Headless build of this project")
    sp.add_argument("--ncs", default="v3.3.0", help="toolchain version (default v3.3.0)")
    sp.add_argument("--sdk", default="", help="SDK folder to build against (default: --ncs)")
    sp.add_argument("--board", default="nrf5340dk/nrf5340/cpuapp")
    sp.add_argument("--pristine", action="store_true")
    sp.set_defaults(func=cmd_build)

    sp = sub.add_parser("shell", help="Interactive shell in the build env")
    sp.add_argument("--ncs", default="v3.3.0")
    sp.add_argument("--sdk", default="")
    sp.set_defaults(func=cmd_shell)

    sp = sub.add_parser("flash", help="Flash the built .hex from the host (J-Link)")
    sp.add_argument("--hex", default="", help="explicit .hex (else auto-pick build/merged.hex)")
    sp.add_argument("--serial", default="", help="probe serial number if more than one")
    sp.add_argument("--core", default="Application")
    sp.add_argument("--nrfutil", default="", help="path to nrfutil (else PATH / C:\\ncs)")
    sp.set_defaults(func=cmd_flash)

    args = p.parse_args()
    try:
        args.func(args)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)


if __name__ == "__main__":
    main()
