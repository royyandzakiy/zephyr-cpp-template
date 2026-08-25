#!/usr/bin/env python3
"""
ncs.py -- one CLI to install, register and use Zephyr SDKs.

Three kinds of SDK live side by side in ONE store directory (default ~/ncs,
fully configurable -- see `ncs.py config`):

    ncs      official nRF Connect SDK   (nrfutil toolchain + sdk-nrf manifest)
    vanilla  upstream Zephyr            (Zephyr SDK toolchain + zephyr manifest)
    custom   your own fork / manifest   (any git URL, built with either toolchain)

Every install ends with registration, so the nRF Connect for VS Code extension
finds the result. See docs/ncs-cli.md for the long version.

Quick start (native, e.g. inside WSL as a normal user -- no root, no /root/ncs):

    python3 scripts/ncs.py bootstrap                     # nrfutil -> ~/.local/bin
    python3 scripts/ncs.py config set install-dir ~/ncs
    python3 scripts/ncs.py install ncs v3.3.0
    python3 scripts/ncs.py install vanilla v4.2.2
    python3 scripts/ncs.py install custom my-sdk git@github.com:me/sdk-nrf.git \
            --rev my-branch --toolchain v3.3.0
    python3 scripts/ncs.py register --vscode
    python3 scripts/ncs.py doctor

Put `--docker` BEFORE the subcommand to run the same command inside the
`ncs-base` container against the `ncs-sdks` volume instead of this filesystem.
"""
from __future__ import annotations

import argparse
import configparser
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

# --------------------------------------------------------------------------- #
# constants
# --------------------------------------------------------------------------- #

ROOT = Path(__file__).resolve().parents[1]                      # project root
SELF = Path(__file__).resolve().relative_to(ROOT).as_posix()    # "scripts/ncs.py"
PROJECT = ROOT.name

IN_CONTAINER = Path("/.dockerenv").exists() or os.environ.get("NCS_IN_CONTAINER") == "1"

NCS_MANIFEST = "https://github.com/nrfconnect/sdk-nrf"
ZEPHYR_MANIFEST = "https://github.com/zephyrproject-rtos/zephyr"
SDK_NG_DL = "https://github.com/zephyrproject-rtos/sdk-ng/releases/download"
NRFUTIL_DL = "https://files.nordicsemi.com/artifactory/swtools/external/nrfutil/executables"

# Folder names inside the store that are NOT SDKs.
RESERVED = {"toolchains", "downloads", "tmp", "sdk-manager", ".venv", ".cache"}

# Per-SDK marker this tool writes, so list/env/build never have to guess which
# toolchain an SDK belongs to.
MARKER = ".ncs-sdk.json"

DEFAULTS = {
    # where SDKs + toolchains are installed (the "store")
    "install_dir": str(Path.home() / "ncs"),
    # "local" = this filesystem; "docker" = the ncs-base image + ncs-sdks volume
    "backend": "local",
    # defaults used when a flag is omitted
    "toolchain": "v3.3.0",
    "board": "nrf5340dk/nrf5340/cpuapp",
    "zephyr_sdk_version": "0.17.0",
    "zephyr_sdk_targets": ["arm-zephyr-eabi", "x86_64-zephyr-elf"],
    # docker backend
    "image": "ncs-base:latest",
    "volume": "ncs-sdks",
    "ssh_volume": "ncs-ssh",
    "container_install_dir": "/root/ncs",
    "docker_platform": "linux/amd64",
}

CONFIG_KEYS = {  # cli name -> config key
    "install-dir": "install_dir",
    "backend": "backend",
    "toolchain": "toolchain",
    "board": "board",
    "zephyr-sdk-version": "zephyr_sdk_version",
    "image": "image",
    "volume": "volume",
    "container-install-dir": "container_install_dir",
}


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #

def info(msg):
    print(f"==> {msg}")


def warn(msg):
    print(f"!!  {msg}", file=sys.stderr)


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def run(argv, cwd=None, env=None, check=True):
    """Run a command (argv list, no shell), echoing it first."""
    where = f"   (cwd: {cwd})" if cwd else ""
    print("+ " + " ".join(shlex.quote(str(c)) for c in argv) + where)
    return subprocess.run([str(c) for c in argv], cwd=str(cwd) if cwd else None,
                          env=env, check=check)


def which(name):
    return shutil.which(name)


def md5(text):
    return hashlib.md5(text.encode()).hexdigest()


def rmtree(path):
    """rmtree that survives read-only files (git objects, Windows)."""
    def on_error(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)
    shutil.rmtree(path, onerror=on_error)


def download(url, dest):
    info(f"downloading {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(url) as resp, open(tmp, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            print(f"\r    {done * 100 // total}%" if total
                  else f"\r    {done >> 20} MiB", end="", flush=True)
    print()
    tmp.replace(dest)


def untar(archive, dest):
    """Extract with the system tar when available (much faster), else tarfile."""
    dest.mkdir(parents=True, exist_ok=True)
    if which("tar"):
        run(["tar", "-xf", archive, "-C", dest])
        return
    info(f"extracting {archive.name} with python tarfile (slow)")
    with tarfile.open(archive) as tf:
        try:
            tf.extractall(dest, filter="tar")      # python 3.12+
        except TypeError:
            tf.extractall(dest)


def host_tag():
    """Zephyr SDK / nrfutil host fragment for this machine."""
    machine = platform.machine().lower()
    arch = {"x86_64": "x86_64", "amd64": "x86_64",
            "aarch64": "aarch64", "arm64": "aarch64"}.get(machine, machine)
    if sys.platform.startswith("linux"):
        return f"linux-{arch}"
    if sys.platform == "darwin":
        return f"macos-{arch}"
    return f"windows-{arch}"


# --------------------------------------------------------------------------- #
# config -- this is what makes the store location changeable
# --------------------------------------------------------------------------- #

def config_file():
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData/Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "ncs-tool" / "config.json"


def load_config():
    cfg = dict(DEFAULTS)
    path = config_file()
    if path.exists():
        try:
            cfg.update(json.loads(path.read_text()))
        except json.JSONDecodeError as exc:
            warn(f"ignoring unreadable {path}: {exc}")
    return cfg


def save_config(cfg):
    """Persist only what differs from the defaults."""
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    diff = {k: v for k, v in cfg.items() if DEFAULTS.get(k) != v}
    path.write_text(json.dumps(diff, indent=2, sort_keys=True) + "\n")
    return path


class Ctx:
    """Resolved settings for one invocation.

    Store directory precedence:
        --install-dir  >  $NCS_INSTALL_DIR  >  config file  >  ~/ncs
    In the docker backend the *container* path is used instead (see
    `container-install-dir`), because that is where the volume is mounted.
    """

    def __init__(self, args):
        self.cfg = load_config()
        self.args = args
        self.backend = getattr(args, "backend", None) or (
            "docker" if getattr(args, "docker", False) else self.cfg["backend"])
        if IN_CONTAINER:
            self.backend = "local"

        raw = (getattr(args, "install_dir", None)
               or os.environ.get("NCS_INSTALL_DIR")
               or self.cfg["install_dir"])
        store = Path(os.path.expandvars(raw)).expanduser()
        self.store = store if IN_CONTAINER else Path(os.path.abspath(store))

    @property
    def toolchains(self):
        return self.store / "toolchains"

    @property
    def venv(self):
        return self.store / ".venv"

    @property
    def venv_bin(self):
        return self.venv / ("Scripts" if sys.platform == "win32" else "bin")

    def get(self, key):
        return self.cfg[key]


# --------------------------------------------------------------------------- #
# docker backend -- it simply re-runs THIS script inside the ncs-base
# container, so there is exactly one implementation of every command.
# --------------------------------------------------------------------------- #

GLOBAL_VALUE_FLAGS = {"--install-dir", "--backend"}
GLOBAL_BOOL_FLAGS = {"--docker"}


def strip_global_flags(argv):
    out, skip = [], False
    for tok in argv:
        if skip:
            skip = False
            continue
        if tok in GLOBAL_VALUE_FLAGS:
            skip = True
            continue
        if tok in GLOBAL_BOOL_FLAGS or any(
                tok.startswith(flag + "=") for flag in GLOBAL_VALUE_FLAGS):
            continue
        out.append(tok)
    return out


def delegate_to_docker(ctx, interactive=False):
    """Re-invoke this script in the container, against the SDK volume."""
    store = ctx.get("container_install_dir")
    dest = f"/workspaces/{PROJECT}"
    cmd = ["docker", "run", "--rm", "--platform", ctx.get("docker_platform")]
    if interactive:
        cmd += ["-it"] if (sys.stdin.isatty() and sys.stdout.isatty()) else ["-i"]
    cmd += [
        "-v", f"{ctx.get('volume')}:{store}",
        "-v", f"{ctx.get('ssh_volume')}:/root/.ssh",
        "-v", f"{ROOT}:{dest}",
        "-w", dest,
        "-e", "NCS_IN_CONTAINER=1",
        "-e", f"NCS_INSTALL_DIR={store}",
        ctx.get("image"), "python3", SELF,
        "--install-dir", store,
    ] + strip_global_flags(sys.argv[1:])
    return run(cmd, check=False).returncode


# --------------------------------------------------------------------------- #
# store inspection
# --------------------------------------------------------------------------- #

def read_marker(sdk):
    path = sdk / MARKER
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def write_marker(sdk, data):
    (sdk / MARKER).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def west_manifest(sdk):
    """Manifest recorded in the workspace's .west/config, if any."""
    cfgfile = sdk / ".west" / "config"
    if not cfgfile.exists():
        return ""
    parser = configparser.ConfigParser()
    try:
        parser.read(cfgfile)
        return (parser.get("manifest", "url", fallback="")
                or parser.get("manifest", "path", fallback=""))
    except configparser.Error:
        return ""


def zephyr_pkg_dir(sdk):
    return sdk / "zephyr" / "share" / "zephyr-package" / "cmake"


def scan_sdks(ctx):
    """Every west workspace in the store -- official, vanilla or custom.

    The test is the same one the nRF Connect extension effectively applies: a
    folder is an SDK if it has zephyr/share/zephyr-package/cmake. Folder names
    are irrelevant, so custom SDKs with any name are found too.
    """
    if not ctx.store.is_dir():
        return []
    found = []
    for entry in sorted(ctx.store.iterdir()):
        if not entry.is_dir() or entry.name in RESERVED:
            continue
        pkg = zephyr_pkg_dir(entry)
        if not pkg.is_dir():
            continue
        marker = read_marker(entry)
        found.append({
            "name": entry.name,
            "path": entry,
            "pkg": pkg,
            "kind": marker.get("kind") or ("ncs" if (entry / "nrf").is_dir()
                                           else "vanilla"),
            "toolchain": marker.get("toolchain", ""),
            "zephyr_sdk": marker.get("zephyr_sdk", ""),
            "manifest": marker.get("url") or west_manifest(entry),
        })
    return found


def find_sdk(ctx, name):
    for sdk in scan_sdks(ctx):
        if sdk["name"] == name:
            return sdk
    die(f"no SDK named '{name}' in {ctx.store}  (see: {SELF} list)")


def load_nrf_toolchains(ctx):
    """Parse toolchains/toolchains.json -- nrfutil's own toolchain index."""
    path = ctx.toolchains / "toolchains.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return data[0].get("toolchains", []) if data else []
    return data.get("toolchains", []) if isinstance(data, dict) else []


def nrf_toolchain_dir(ctx, ncs_version):
    for entry in load_nrf_toolchains(ctx):
        if ncs_version in entry.get("ncs_versions", []):
            bundle = entry.get("identifier", {}).get("bundle_id") or entry.get("path")
            if bundle:
                path = Path(bundle)
                return path if path.is_absolute() else ctx.toolchains / bundle
    return None


def zephyr_sdks(ctx):
    if not ctx.toolchains.is_dir():
        return []
    return sorted(p for p in ctx.toolchains.glob("zephyr-sdk-*") if p.is_dir())


# --------------------------------------------------------------------------- #
# registration -- how the nRF Connect extension actually discovers things
#
#   toolchains : the extension runs nrfutil with an --install-dir taken from
#                the setting `nrf-connect.toolchainManager.installDirectory`
#   SDKs       : the extension reads the CMake *user package registry*
#                ~/.cmake/packages/Zephyr (what `west zephyr-export` writes)
#
# Neither is guaranteed by an nrfutil/west install, and ~/.cmake is easy to
# lose (fresh container, new user), so we (re)create the entries here.
# --------------------------------------------------------------------------- #

VSCODE_SETTING = "nrf-connect.toolchainManager.installDirectory"


def cmake_registry(package):
    return Path.home() / ".cmake" / "packages" / package


def register_package(package, path):
    """Write one CMake user-package-registry entry. True if it was new.

    The file name is a hash for de-duplication only; CMake reads the *content*
    of every file in the directory and treats it as a package path.
    """
    reg = cmake_registry(package)
    reg.mkdir(parents=True, exist_ok=True)
    text = str(path)
    entry = reg / md5(text)
    if entry.exists() and entry.read_text().strip() == text:
        return False
    entry.write_text(text)
    return True


def prune_registry():
    """Drop entries whose target directory is gone (removed/renamed SDKs)."""
    removed = 0
    for package in ("Zephyr", "ZephyrUnittest", "Zephyr-sdk"):
        reg = cmake_registry(package)
        if not reg.is_dir():
            continue
        for entry in reg.iterdir():
            if entry.is_file() and not Path(entry.read_text().strip()).is_dir():
                entry.unlink()
                removed += 1
    return removed


def register_all(ctx, quiet=False):
    """Register every SDK and Zephyr SDK toolchain found in the store."""
    stale = prune_registry()
    count = 0
    for sdk in scan_sdks(ctx):
        new = register_package("Zephyr", sdk["pkg"])
        unittest = sdk["path"] / "zephyr" / "share" / "zephyrunittest-package" / "cmake"
        if unittest.is_dir():
            register_package("ZephyrUnittest", unittest)
        count += 1
        if not quiet:
            print(f"    {'+' if new else '='} SDK       {sdk['name']:<24} {sdk['pkg']}")
    for sdk in zephyr_sdks(ctx):
        cmake = sdk / "cmake"
        if cmake.is_dir():
            new = register_package("Zephyr-sdk", cmake)
            if not quiet:
                print(f"    {'+' if new else '='} toolchain {sdk.name:<24} {cmake}")
    if not quiet:
        extra = (f", pruned {stale} stale entr{'y' if stale == 1 else 'ies'}"
                 if stale else "")
        info(f"registered {count} SDK(s) in {cmake_registry('Zephyr')}{extra}")
    return count


def vscode_snippet(ctx):
    return f'"{VSCODE_SETTING}": "{ctx.store.as_posix()}"'


SETTING_RE = re.compile(r'"' + re.escape(VSCODE_SETTING) + r'"\s*:\s*"[^"]*"')


def update_vscode_settings(ctx):
    """Point the extension at the store.

    VS Code settings are JSONC, so this edits the text rather than reserialising
    it -- comments in the file survive. A .bak copy is left behind.
    """
    path = ROOT / ".vscode" / "settings.json"
    value = ctx.store.as_posix()
    entry = f'"{VSCODE_SETTING}": "{value}"'

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({VSCODE_SETTING: value}, indent=4) + "\n")
        info(f"set {VSCODE_SETTING} = {ctx.store} in {path}")
        return

    raw = path.read_text()
    if SETTING_RE.search(raw):
        updated = SETTING_RE.sub(entry, raw)
        if updated == raw:
            info(f"{path} already points at {ctx.store}")
            return
    else:
        head, brace, tail = raw.partition("{")
        if not brace:
            die(f"{path} does not look like a settings file")
        indent = "\t" if "\n\t" in raw else "    "
        updated = (f"{head}{{\n"
                   f"{indent}// where SDKs + toolchains live "
                   f"(written by `{SELF} register --vscode`)\n"
                   f"{indent}{entry},{tail}")

    shutil.copyfile(path, path.with_name("settings.json.bak"))
    path.write_text(updated)
    info(f"set {VSCODE_SETTING} = {ctx.store} in {path}  (backup: settings.json.bak)")


# --------------------------------------------------------------------------- #
# tool wrappers
# --------------------------------------------------------------------------- #

def nrfutil(ctx):
    exe = which("nrfutil") or which("nrfutil.exe")
    if not exe and sys.platform == "win32" and Path(r"C:\ncs\nrfutil.exe").exists():
        exe = r"C:\ncs\nrfutil.exe"
    if not exe:
        die(f"nrfutil is not on PATH. Install it with `{SELF} bootstrap`, "
            f"or use --docker.")
    return exe


def point_nrfutil_at_store(ctx):
    """Make nrfutil install into -- and look inside -- our store.

    Each nrfutil manager keeps its own install-dir; the VS Code extension uses
    a third setting. All of them must agree, or you get the classic
    "installed but not listed" / "SDK not configured".
    """
    exe = nrfutil(ctx)
    ctx.store.mkdir(parents=True, exist_ok=True)
    run([exe, "toolchain-manager", "config", "--set", f"install-dir={ctx.store}"])
    # sdk-manager is optional -- not every nrfutil install has that command.
    run([exe, "sdk-manager", "config", "install-dir", "set", str(ctx.store)],
        check=False)


def in_toolchain(ctx, ncs_version, argv, cwd=None, check=True):
    """Run argv inside an nrfutil toolchain env (its own west/cmake/python)."""
    return run([nrfutil(ctx), "toolchain-manager", "launch",
                "--ncs-version", ncs_version, "--"] + list(argv),
               cwd=cwd, check=check)


def ensure_nrf_toolchain(ctx, ncs_version):
    """Install the NCS toolchain bundle for `ncs_version` if it is missing."""
    point_nrfutil_at_store(ctx)
    path = nrf_toolchain_dir(ctx, ncs_version)
    if path and path.is_dir():
        info(f"NCS toolchain {ncs_version} already installed ({path.name})")
        return path
    info(f"installing NCS toolchain {ncs_version}")
    # NOTE: nrfutil appends "/toolchains" itself, so pass the STORE here, not
    # store/toolchains.
    run([nrfutil(ctx), "toolchain-manager", "install",
         "--ncs-version", ncs_version, "--install-dir", ctx.store])
    path = nrf_toolchain_dir(ctx, ncs_version)
    if not path:
        die(f"nrfutil reported success but no toolchain for {ncs_version} is "
            f"listed in {ctx.toolchains / 'toolchains.json'}")
    return path


def ensure_venv(ctx):
    """A store-local venv holding `west`, for vanilla-Zephyr work.

    nrfutil's toolchain bundles ship their own west/python; upstream Zephyr does
    not. The venv lives in the store, so it is shared and persistent like
    everything else.
    """
    west = ctx.venv_bin / ("west.exe" if sys.platform == "win32" else "west")
    if west.exists():
        return west
    info(f"creating a python venv for west in {ctx.venv}")
    ctx.store.mkdir(parents=True, exist_ok=True)
    run([sys.executable, "-m", "venv", str(ctx.venv)])
    pip = ctx.venv_bin / ("pip.exe" if sys.platform == "win32" else "pip")
    run([pip, "install", "--upgrade", "pip", "wheel"])
    run([pip, "install", "west"])
    return west


def venv_pip(ctx):
    return ctx.venv_bin / ("pip.exe" if sys.platform == "win32" else "pip")


# --------------------------------------------------------------------------- #
# commands: bootstrap / config
# --------------------------------------------------------------------------- #

NRFUTIL_TRIPLES = {
    "linux-x86_64": "x86_64-unknown-linux-gnu",
    "linux-aarch64": "aarch64-unknown-linux-gnu",
    "macos-x86_64": "x86_64-apple-darwin",
    "macos-aarch64": "aarch64-apple-darwin",
    "windows-x86_64": "x86_64-pc-windows-msvc",
}


def cmd_bootstrap(ctx):
    """Install nrfutil + its sub-commands, without root."""
    args = ctx.args
    tag = host_tag()
    triple = NRFUTIL_TRIPLES.get(tag)
    if not triple:
        die(f"no nrfutil build known for {tag}; install it manually")
    exe_name = "nrfutil.exe" if tag.startswith("windows") else "nrfutil"
    bindir = Path(args.bin_dir).expanduser()
    dest = bindir / exe_name

    if dest.exists() and not args.force:
        info(f"{dest} already exists (--force to re-download)")
    else:
        download(f"{NRFUTIL_DL}/{triple}/{exe_name}", dest)
        dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        info(f"installed {dest}")

    for command in ("toolchain-manager", "sdk-manager", "device"):
        run([dest, "install", command], check=False)

    if str(bindir) not in os.environ.get("PATH", "").split(os.pathsep):
        print(f"\n{bindir} is not on your PATH yet. Add it:\n"
              f"    echo 'export PATH=\"{bindir}:$PATH\"' >> ~/.bashrc && exec $SHELL\n")
    print(f"Next:  {SELF} config set install-dir {ctx.store}")


def cmd_config(ctx):
    args = ctx.args
    cfg = load_config()

    if args.action == "show":
        exists = "exists" if ctx.store.is_dir() else "MISSING"
        created = "" if config_file().exists() else "   (not created yet -- defaults)"
        print(f"config file : {config_file()}{created}")
        print(f"store       : {ctx.store}   [{exists}]")
        print(f"backend     : {ctx.backend}")
        print()
        for cli_name, key in CONFIG_KEYS.items():
            mark = " " if cfg[key] == DEFAULTS[key] else "*"
            print(f" {mark} {cli_name:<22} {cfg[key]}")
        print("\n* = overridden.  $NCS_INSTALL_DIR and --install-dir win over the file.")
        return

    key = CONFIG_KEYS.get(args.key)
    if not key:
        die(f"unknown key '{args.key}'. Known keys: {', '.join(CONFIG_KEYS)}")

    if args.action == "unset":
        cfg[key] = DEFAULTS[key]
        info(f"{args.key} reset to {DEFAULTS[key]}")
        print(f"    saved to {save_config(cfg)}")
        return

    value = args.value
    if key == "install_dir":
        value = str(Path(os.path.expandvars(value)).expanduser())
    cfg[key] = value
    path = save_config(cfg)
    info(f"{args.key} = {value}")
    print(f"    saved to {path}")

    if key == "install_dir":
        ctx.store = Path(value)
        ctx.store.mkdir(parents=True, exist_ok=True)
        if which("nrfutil") or which("nrfutil.exe"):
            point_nrfutil_at_store(ctx)
        print(f"\nThe VS Code extension has its OWN setting for this -- write it with:\n"
              f"    {SELF} register --vscode        ({vscode_snippet(ctx)})\n"
              f"If you use the devcontainer, also change the volume mount target and\n"
              f"NCS_INSTALL_DIR (docs/ncs-cli.md, 'Moving the store').")


# --------------------------------------------------------------------------- #
# commands: install
# --------------------------------------------------------------------------- #

def west_workspace(ctx, dest, url, rev, manifest_file, runner, shallow, blobs):
    """west init -> west update -> west zephyr-export, through `runner`."""
    init = ["west", "init", "-m", url]
    if rev:
        init += ["--mr", rev]
    if manifest_file:
        init += ["--mf", manifest_file]
    init += [str(dest)]

    update = ["west", "update"]
    if shallow:
        update += ["--narrow", "-o=--depth=1"]

    # accept-new lets a first clone from a new host proceed without a prompt.
    previous = os.environ.get("GIT_SSH_COMMAND")
    os.environ["GIT_SSH_COMMAND"] = "ssh -o StrictHostKeyChecking=accept-new"
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        runner(init, cwd=dest.parent)
        runner(update, cwd=dest)
        if blobs:
            runner(["west", "blobs", "fetch", "hal_nordic"], cwd=dest, check=False)
        # Registers the CMake package -- nice when it works, but it needs cmake
        # on PATH, and register_all() below covers us regardless.
        runner(["west", "zephyr-export"], cwd=dest, check=False)
    finally:
        if previous is None:
            os.environ.pop("GIT_SSH_COMMAND", None)
        else:
            os.environ["GIT_SSH_COMMAND"] = previous


def finish_install(ctx, dest, kind, extra):
    write_marker(dest, dict(kind=kind, **extra))
    print()
    register_all(ctx)
    print(f"\n{kind} SDK '{dest.name}' is ready at {dest}.\n"
          f"  VS Code : nRF Connect -> Refresh SDKs -> Add build configuration\n"
          f"  CLI     : {SELF} build --sdk {dest.name}")


def nrf_runner(ctx, toolchain):
    def runner(argv, cwd=None, check=True):
        return in_toolchain(ctx, toolchain, argv, cwd=cwd, check=check)
    return runner


def venv_runner(ctx, env=None):
    """Runner for vanilla work: `west` means the store venv's west."""
    west = ensure_venv(ctx)

    def runner(argv, cwd=None, check=True):
        argv = list(argv)
        if argv and argv[0] == "west":
            argv[0] = str(west)
        return run(argv, cwd=cwd, env=env, check=check)
    return runner


def cmd_install_ncs(ctx):
    """Official nRF Connect SDK: nrfutil toolchain + sdk-nrf west workspace."""
    args = ctx.args
    version = args.version
    dest = ctx.store / (args.name or version)
    if dest.exists() and not args.reuse:
        die(f"{dest} already exists. Delete it (`{SELF} remove {dest.name}`), "
            f"pass --name to install alongside it, or --reuse to continue into it.")

    ensure_nrf_toolchain(ctx, version)
    if zephyr_pkg_dir(dest).is_dir():
        info(f"sources already present in {dest}")
    else:
        info(f"fetching nRF Connect SDK {version} into {dest}")
        west_workspace(ctx, dest, args.url, version, args.manifest_file,
                       nrf_runner(ctx, version), args.shallow, args.blobs)
    finish_install(ctx, dest, "ncs",
                   {"version": version, "toolchain": version, "url": args.url})


def cmd_install_vanilla(ctx):
    """Upstream Zephyr: Zephyr SDK toolchain + zephyr west workspace."""
    args = ctx.args
    version = args.version
    dest = ctx.store / (args.name or f"zephyr-{version}")
    if dest.exists() and not args.reuse:
        die(f"{dest} already exists. Delete it (`{SELF} remove {dest.name}`), "
            f"pass --name to install alongside it, or --reuse to continue into it.")

    sdk_version = args.zephyr_sdk_version or ctx.get("zephyr_sdk_version")
    targets = args.target or ctx.get("zephyr_sdk_targets")
    sdk_dir = install_zephyr_sdk(ctx, sdk_version, targets)

    if zephyr_pkg_dir(dest).is_dir():
        info(f"sources already present in {dest}")
    else:
        info(f"fetching Zephyr {version} into {dest}")
        west_workspace(ctx, dest, args.url, version, args.manifest_file,
                       venv_runner(ctx), args.shallow, False)
        requirements = dest / "zephyr" / "scripts" / "requirements.txt"
        if not args.no_python_deps and requirements.exists():
            info("installing Zephyr's python requirements into the store venv")
            run([venv_pip(ctx), "install", "-r", str(requirements)], check=False)

    finish_install(ctx, dest, "vanilla",
                   {"version": version, "zephyr_sdk": sdk_dir.name, "url": args.url})


def install_zephyr_sdk(ctx, version, targets):
    """Download + set up an upstream Zephyr SDK (the vanilla toolchain)."""
    dest = ctx.toolchains / f"zephyr-sdk-{version}"
    if dest.is_dir():
        info(f"Zephyr SDK {version} already installed ({dest})")
        return dest

    tag = host_tag()
    if tag.startswith("windows"):
        die("installing the Zephyr SDK natively on Windows is not supported here "
            "-- run this inside WSL, or use --docker")

    archive_name = f"zephyr-sdk-{version}_{tag}_minimal.tar.xz"
    archive = ctx.toolchains / "downloads" / archive_name
    if not archive.exists():
        download(f"{SDK_NG_DL}/v{version}/{archive_name}", archive)

    untar(archive, ctx.toolchains)
    if not dest.is_dir():
        die(f"expected {dest} after extracting {archive_name}")

    # setup.sh: -t <target> installs one toolchain, -h host tools, -c registers
    # the Zephyr-sdk CMake package. With flags it is non-interactive.
    setup = ["./setup.sh", "-h", "-c"]
    for target in targets:
        setup += ["-t", target]
    run(setup, cwd=dest)
    archive.unlink(missing_ok=True)
    # Belt and braces: register it ourselves too, in case -c did nothing.
    register_package("Zephyr-sdk", dest / "cmake")
    return dest


def cmd_install_custom(ctx):
    """Any manifest repo (your fork, a private SDK) + the toolchain it needs."""
    args = ctx.args
    dest = ctx.store / args.name
    if dest.exists() and not args.reuse:
        die(f"{dest} already exists. Delete it (`{SELF} remove {args.name}`) "
            f"or pass --reuse to continue into it.")

    if args.vanilla_toolchain:
        sdk_dir = install_zephyr_sdk(ctx, args.vanilla_toolchain,
                                     args.target or ctx.get("zephyr_sdk_targets"))
        runner = venv_runner(ctx)
        extra = {"zephyr_sdk": sdk_dir.name}
    else:
        toolchain = args.toolchain or ctx.get("toolchain")
        ensure_nrf_toolchain(ctx, toolchain)
        runner = nrf_runner(ctx, toolchain)
        extra = {"toolchain": toolchain}

    rev = f" (rev {args.rev})" if args.rev else ""
    info(f"installing custom SDK '{args.name}' from {args.url}{rev}")
    if args.url.startswith(("git@", "ssh://")):
        print("    SSH URL -- your key/agent must already be authorized for that "
              "host.\n    In the devcontainer: `ncs-ssh-setup <host>` first.")
    west_workspace(ctx, dest, args.url, args.rev, args.manifest_file,
                   runner, args.shallow, args.blobs)
    finish_install(ctx, dest, "custom",
                   dict(url=args.url, rev=args.rev, **extra))


def cmd_install_toolchain(ctx):
    """A toolchain only -- no SDK sources."""
    args = ctx.args
    if args.zephyr_sdk:
        path = install_zephyr_sdk(ctx, args.version,
                                  args.target or ctx.get("zephyr_sdk_targets"))
    else:
        path = ensure_nrf_toolchain(ctx, args.version)
    info(f"toolchain ready: {path}")


# --------------------------------------------------------------------------- #
# commands: list / remove / register / env / doctor
# --------------------------------------------------------------------------- #

def registered_paths(package="Zephyr"):
    reg = cmake_registry(package)
    if not reg.is_dir():
        return set()
    return {entry.read_text().strip() for entry in reg.iterdir() if entry.is_file()}


def cmd_list(ctx):
    sdks = scan_sdks(ctx)
    registered = registered_paths()

    if ctx.args.json:
        print(json.dumps({
            "store": str(ctx.store),
            "sdks": [{"name": s["name"], "kind": s["kind"], "path": str(s["path"]),
                      "toolchain": s["toolchain"] or s["zephyr_sdk"],
                      "manifest": s["manifest"],
                      "registered": str(s["pkg"]) in registered} for s in sdks],
            "nrf_toolchains": [{"bundle": t.get("identifier", {}).get("bundle_id", ""),
                                "versions": t.get("ncs_versions", [])}
                               for t in load_nrf_toolchains(ctx)],
            "zephyr_sdks": [p.name for p in zephyr_sdks(ctx)],
        }, indent=2))
        return

    print(f"store: {ctx.store}")
    print(f"\nSDKs ({len(sdks)}):")
    if not sdks:
        print(f"    (none)   ->   {SELF} install ncs v3.3.0")
    for sdk in sdks:
        flag = "registered" if str(sdk["pkg"]) in registered else "NOT REGISTERED"
        toolchain = sdk["toolchain"] or sdk["zephyr_sdk"] or "?"
        print(f"    {sdk['name']:<24} {sdk['kind']:<8} {toolchain:<18} [{flag}]")
        if "://" in sdk["manifest"] or "@" in sdk["manifest"]:
            print(f"        {sdk['manifest']}")

    entries = load_nrf_toolchains(ctx)
    print(f"\nnRF Connect toolchains ({len(entries)}):")
    for entry in entries or []:
        versions = ",".join(entry.get("ncs_versions", [])) or "?"
        print(f"    {versions:<24} {entry.get('identifier', {}).get('bundle_id', '?')}")
    if not entries:
        print("    (none)")

    sdk_dirs = zephyr_sdks(ctx)
    print(f"\nZephyr SDKs / vanilla toolchains ({len(sdk_dirs)}):")
    for path in sdk_dirs:
        print(f"    {path.name}")
    if not sdk_dirs:
        print("    (none)")


def cmd_remove(ctx):
    args = ctx.args
    target = ctx.store / args.name
    if not target.is_dir():
        die(f"{target} does not exist")
    if target.resolve() == ctx.store.resolve():
        die("refusing to delete the store itself")
    if not args.yes:
        if input(f"Delete {target} permanently? [y/N] ").strip().lower() not in ("y", "yes"):
            print("aborted")
            return
    rmtree(target)
    info(f"removed {target}")
    pruned = prune_registry()
    info(f"pruned {pruned} CMake registry entr{'y' if pruned == 1 else 'ies'}")


def cmd_register(ctx):
    if not ctx.store.is_dir():
        die(f"store {ctx.store} does not exist")
    register_all(ctx)
    if ctx.args.vscode:
        update_vscode_settings(ctx)
    else:
        print(f"\nThe extension needs one more thing -- its install directory:\n"
              f"    {vscode_snippet(ctx)}\n"
              f"    write it with:  {SELF} register --vscode")
    if IN_CONTAINER:
        print("\nNote: ~/.cmake lives in the container's writable layer, so this\n"
              "must run in the SAME container VS Code attaches to. The\n"
              "devcontainer does that via postStartCommand.")


def sdk_toolchain(ctx, sdk):
    """The NCS toolchain version an SDK builds with ('' for vanilla ones)."""
    if sdk["kind"] not in ("ncs", "custom"):
        return ""
    if sdk["toolchain"]:
        return sdk["toolchain"]
    if sdk["zephyr_sdk"]:            # explicitly a vanilla-toolchain custom SDK
        return ""
    fallback = ctx.get("toolchain")
    warn(f"'{sdk['name']}' has no recorded toolchain -- assuming {fallback} "
         f"(set it in {sdk['path'] / MARKER})")
    return fallback


def cmd_env(ctx):
    """Print shell exports:  eval "$(python3 scripts/ncs.py env v3.3.0)" """
    sdk = find_sdk(ctx, ctx.args.name)
    zephyr_base = (sdk["path"] / "zephyr").as_posix()
    lines = [f'export ZEPHYR_BASE="{zephyr_base}"',
             'export ZEPHYR_TOOLCHAIN_VARIANT="zephyr"']

    version = sdk_toolchain(ctx, sdk)
    if version:
        toolchain = nrf_toolchain_dir(ctx, version)
        if not toolchain:
            die(f"toolchain {version} for '{sdk['name']}' is not installed "
                f"(`{SELF} install toolchain {version}`)")
        toolchain = toolchain.as_posix()
        ld = [f"{toolchain}/usr/local/lib", f"{toolchain}/opt/lib"]
        if os.environ.get("LD_LIBRARY_PATH"):
            ld.append(os.environ["LD_LIBRARY_PATH"])
        lines += [
            f'export NCS_TOOLCHAIN_PATH="{toolchain}"',
            f'export ZEPHYR_SDK_INSTALL_DIR="{toolchain}/opt/zephyr-sdk"',
            f'export LD_LIBRARY_PATH="{":".join(ld)}"',
            f'export PATH="{toolchain}/usr/local/bin:{toolchain}/opt/bin:'
            f'{toolchain}/bin:$PATH"',
        ]
    else:
        installed = zephyr_sdks(ctx)
        name = sdk["zephyr_sdk"] or (installed[-1].name if installed else "")
        if not name:
            die(f"no Zephyr SDK installed "
                f"(`{SELF} install toolchain 0.17.0 --zephyr-sdk`)")
        lines += [
            f'export ZEPHYR_SDK_INSTALL_DIR="{(ctx.toolchains / name).as_posix()}"',
            f'export PATH="{ctx.venv_bin.as_posix()}:$PATH"',
        ]

    env_sh = sdk["path"] / "zephyr" / "zephyr-env.sh"
    if env_sh.exists():
        lines.append(f'. "{env_sh.as_posix()}"')
    lines.append(f'echo "using SDK {sdk["name"]} ({sdk["kind"]})" >&2')
    print("\n".join(lines))


def cmd_doctor(ctx):
    ok, bad = [], []

    def check(good, message):
        (ok if good else bad).append(message)

    check(ctx.store.is_dir(),
          f"store {ctx.store} {'exists' if ctx.store.is_dir() else 'is MISSING'}")

    exe = which("nrfutil") or which("nrfutil.exe")
    check(bool(exe), f"nrfutil {'at ' + exe if exe else f'NOT on PATH ({SELF} bootstrap)'}")
    if exe:
        probe = subprocess.run([exe, "toolchain-manager", "config", "--show"],
                               capture_output=True, text=True)
        shown = (probe.stdout + probe.stderr).strip().replace("\n", " ")
        if probe.returncode != 0:
            ok.append("nrfutil install-dir: could not query (harmless)")
        else:
            check(str(ctx.store) in shown,
                  f"nrfutil toolchain-manager install-dir -> {shown}")

    sdks = scan_sdks(ctx)
    check(bool(sdks), f"{len(sdks)} SDK(s) in the store")
    registered = registered_paths()
    for sdk in sdks:
        listed = str(sdk["pkg"]) in registered
        check(listed, f"SDK '{sdk['name']}' {'is' if listed else 'is NOT'} in the "
                      f"CMake registry ({cmake_registry('Zephyr')})")
    stale = [entry for entry in registered if not Path(entry).is_dir()]
    check(not stale,
          f"{len(stale)} stale CMake registry entr{'y' if len(stale) == 1 else 'ies'}")

    settings = ROOT / ".vscode" / "settings.json"
    raw = settings.read_text() if settings.exists() else ""
    check(VSCODE_SETTING in raw and ctx.store.as_posix() in raw,
          f"{VSCODE_SETTING} points at {ctx.store} in .vscode/settings.json")

    check(bool(load_nrf_toolchains(ctx)) or bool(zephyr_sdks(ctx)),
          "at least one toolchain is installed")

    for line in ok:
        print(f"  ok    {line}")
    for line in bad:
        print(f"  FAIL  {line}")
    if bad:
        print(f"\nMost of these are fixed by:\n"
              f"    {SELF} config set install-dir {ctx.store}\n"
              f"    {SELF} register --vscode\n"
              f"then 'nRF Connect: Refresh SDKs' (or reload the VS Code window).")
        sys.exit(1)
    print("\nAll good -- the extension should list every SDK above.")


# --------------------------------------------------------------------------- #
# commands: build / shell / flash / build-image
# --------------------------------------------------------------------------- #

def sdk_runner(ctx, sdk):
    """A runner that executes west with `sdk`'s own toolchain + ZEPHYR_BASE."""
    env = dict(os.environ)
    env["ZEPHYR_BASE"] = str(sdk["path"] / "zephyr")

    toolchain = sdk_toolchain(ctx, sdk)
    if toolchain:
        if not nrf_toolchain_dir(ctx, toolchain):
            die(f"toolchain {toolchain} is not installed "
                f"(`{SELF} install toolchain {toolchain}`)")

        def runner(argv, cwd=None, check=True):
            return run([nrfutil(ctx), "toolchain-manager", "launch",
                        "--ncs-version", toolchain, "--"] + list(argv),
                       cwd=cwd, env=env, check=check)
        return runner

    installed = zephyr_sdks(ctx)
    name = sdk["zephyr_sdk"] or (installed[-1].name if installed else "")
    if not name:
        die(f"'{sdk['name']}' needs a Zephyr SDK "
            f"(`{SELF} install toolchain 0.17.0 --zephyr-sdk`)")
    env["ZEPHYR_TOOLCHAIN_VARIANT"] = "zephyr"
    env["ZEPHYR_SDK_INSTALL_DIR"] = str(ctx.toolchains / name)
    env["PATH"] = f"{ctx.venv_bin}{os.pathsep}{env.get('PATH', '')}"
    return venv_runner(ctx, env=env)


def pick_sdk(ctx, requested):
    sdks = scan_sdks(ctx)
    if not sdks:
        die(f"no SDK in {ctx.store} -- run `{SELF} install ncs v3.3.0` first")
    if requested:
        return find_sdk(ctx, requested)
    default = ctx.get("toolchain")
    for sdk in sdks:
        if sdk["name"] == default:
            return sdk
    if len(sdks) == 1:
        return sdks[0]
    names = ", ".join(sdk["name"] for sdk in sdks)
    die(f"several SDKs installed -- pick one with --sdk: {names}")


def cmd_build(ctx):
    args = ctx.args
    sdk = pick_sdk(ctx, args.sdk)
    source = Path(args.source).resolve()
    argv = ["west", "build", "-b", args.board, str(source),
            "--build-dir", str(source / args.build_dir)]
    if args.pristine:
        argv += ["-p", "always"]
    argv += args.extra
    sdk_runner(ctx, sdk)(argv, cwd=source)
    print(f"\nbuilt {source.name} for {args.board} with SDK '{sdk['name']}'.")


def cmd_shell(ctx):
    sdk = pick_sdk(ctx, ctx.args.sdk)
    shell = os.environ.get("SHELL") or ("cmd.exe" if sys.platform == "win32"
                                        else "/bin/bash")
    print(f"entering a shell for SDK '{sdk['name']}' -- type `exit` to leave")
    sdk_runner(ctx, sdk)([shell], cwd=Path.cwd(), check=False)


def cmd_flash(ctx):
    """Host-side flash via nrfutil device (J-Link). Never delegated to docker."""
    args = ctx.args
    exe = args.nrfutil or which("nrfutil") or which("nrfutil.exe")
    if not exe and sys.platform == "win32" and Path(r"C:\ncs\nrfutil.exe").exists():
        exe = r"C:\ncs\nrfutil.exe"
    if not exe:
        die("nrfutil not found on PATH; pass --nrfutil <path>")

    hexfile = Path(args.hex) if args.hex else None
    if not hexfile:
        build = ROOT / args.build_dir
        merged = build / "merged.hex"
        hexfile = merged if merged.exists() else next(build.rglob("zephyr.hex"), None)
    if not hexfile or not hexfile.exists():
        die(f"no .hex under {ROOT / args.build_dir} -- build first")

    info(f"flashing {hexfile} (core {args.core})")
    cmd = [exe, "device", "program", "--firmware", str(hexfile), "--core", args.core,
           "--options",
           "chip_erase_mode=ERASE_RANGES_TOUCHED_BY_FIRMWARE,reset=RESET_SYSTEM"]
    if args.serial:
        cmd += ["--serial-number", args.serial]
    run(cmd)


def cmd_build_image(ctx):
    run(["docker", "build", "--platform", ctx.get("docker_platform"),
         "-t", ctx.get("image"), str(ROOT)])
    run(["docker", "volume", "create", ctx.get("volume")], check=False)
    print(f"\nBuilt {ctx.get('image')} and ensured volume '{ctx.get('volume')}'.\n"
          f"Next:  {SELF} --docker install ncs v3.3.0")


# --------------------------------------------------------------------------- #
# argument parsing
# --------------------------------------------------------------------------- #

def add_west_flags(parser, name_flag=True, blobs=True):
    parser.add_argument("--manifest-file", default="",
                        help="manifest file, if not west.yml")
    parser.add_argument("--shallow", action="store_true",
                        help="west update --narrow --depth 1 (much smaller)")
    parser.add_argument("--reuse", action="store_true",
                        help="continue into an existing folder instead of failing")
    if name_flag:
        parser.add_argument("--name", default="",
                            help="folder name in the store (default: the version)")
    if blobs:
        parser.add_argument("--blobs", action="store_true",
                            help="also `west blobs fetch hal_nordic`")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="ncs.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--install-dir",
                        help="store directory (default: config file, else ~/ncs)")
    parser.add_argument("--backend", choices=("local", "docker"),
                        help="run store operations here or in the ncs-base container")
    parser.add_argument("--docker", action="store_true",
                        help="shorthand for --backend docker")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # --- bootstrap / config ------------------------------------------------
    sp = sub.add_parser("bootstrap", help="install nrfutil into ~/.local/bin (no root)")
    sp.add_argument("--bin-dir", default=str(Path.home() / ".local" / "bin"))
    sp.add_argument("--force", action="store_true", help="re-download nrfutil")
    sp.set_defaults(func=cmd_bootstrap, store_cmd=False)

    sp = sub.add_parser("config", help="show/change the store directory and defaults")
    csub = sp.add_subparsers(dest="action", required=True)
    csub.add_parser("show").set_defaults(func=cmd_config, store_cmd=False)
    setp = csub.add_parser("set", help=f"keys: {', '.join(CONFIG_KEYS)}")
    setp.add_argument("key")
    setp.add_argument("value")
    setp.set_defaults(func=cmd_config, store_cmd=False)
    unsetp = csub.add_parser("unset", help="restore a key's default")
    unsetp.add_argument("key")
    unsetp.set_defaults(func=cmd_config, store_cmd=False)

    # --- install -----------------------------------------------------------
    sp = sub.add_parser("install", help="install an SDK or a toolchain")
    isub = sp.add_subparsers(dest="kind", required=True)

    ncsp = isub.add_parser("ncs", help="official nRF Connect SDK")
    ncsp.add_argument("version", nargs="?", default=DEFAULTS["toolchain"],
                      help=f"e.g. v3.3.0 (default {DEFAULTS['toolchain']})")
    ncsp.add_argument("--url", default=NCS_MANIFEST, help="manifest repo")
    add_west_flags(ncsp)
    ncsp.set_defaults(func=cmd_install_ncs, store_cmd=True)

    vanp = isub.add_parser("vanilla", help="upstream Zephyr + a Zephyr SDK toolchain")
    vanp.add_argument("version", nargs="?", default="v4.2.2", help="e.g. v4.2.2")
    vanp.add_argument("--url", default=ZEPHYR_MANIFEST, help="manifest repo")
    vanp.add_argument("--zephyr-sdk-version", default="",
                      help=f"Zephyr SDK version (default {DEFAULTS['zephyr_sdk_version']})")
    vanp.add_argument("--target", action="append",
                      help="toolchain target, repeatable (default: arm + x86_64)")
    vanp.add_argument("--no-python-deps", action="store_true",
                      help="skip zephyr/scripts/requirements.txt")
    add_west_flags(vanp, blobs=False)
    vanp.set_defaults(func=cmd_install_vanilla, store_cmd=True, blobs=False)

    cusp = isub.add_parser("custom", help="your own fork / any manifest repo")
    cusp.add_argument("name", help="folder name in the store, e.g. mycompany-nrf")
    cusp.add_argument("url", help="git CLONE url (ssh or https)")
    cusp.add_argument("--rev", default="", help="branch / tag / commit")
    cusp.add_argument("--toolchain", default="",
                      help=f"NCS toolchain to build it with "
                           f"(default {DEFAULTS['toolchain']})")
    cusp.add_argument("--vanilla-toolchain", default="", metavar="ZEPHYR_SDK_VERSION",
                      help="use a Zephyr SDK instead of an NCS toolchain, e.g. 0.17.0")
    cusp.add_argument("--target", action="append", help="Zephyr SDK target, repeatable")
    add_west_flags(cusp, name_flag=False)
    cusp.set_defaults(func=cmd_install_custom, store_cmd=True)

    tcp = isub.add_parser("toolchain", help="a toolchain only, no SDK sources")
    tcp.add_argument("version", help="NCS version (v3.3.0) or Zephyr SDK version (0.17.0)")
    tcp.add_argument("--zephyr-sdk", action="store_true",
                     help="version is a Zephyr SDK (vanilla) version")
    tcp.add_argument("--target", action="append", help="Zephyr SDK target, repeatable")
    tcp.set_defaults(func=cmd_install_toolchain, store_cmd=True)

    # --- inspect / register ------------------------------------------------
    sp = sub.add_parser("list", help="what is installed in the store")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_list, store_cmd=True)

    sp = sub.add_parser("register", help="make the VS Code extension see everything")
    sp.add_argument("--vscode", action="store_true",
                    help="also write .vscode/settings.json")
    sp.set_defaults(func=cmd_register, store_cmd=True)

    sp = sub.add_parser("remove", help="delete an SDK from the store")
    sp.add_argument("name")
    sp.add_argument("-y", "--yes", action="store_true")
    sp.set_defaults(func=cmd_remove, store_cmd=True)

    sp = sub.add_parser("env", help='shell exports: eval "$(ncs.py env <name>)"')
    sp.add_argument("name")
    sp.set_defaults(func=cmd_env, store_cmd=True)

    sp = sub.add_parser("doctor", help="diagnose SDK/toolchain discovery problems")
    sp.set_defaults(func=cmd_doctor, store_cmd=True)

    # --- use ---------------------------------------------------------------
    sp = sub.add_parser("build", help="headless west build with a chosen SDK")
    sp.add_argument("--sdk", default="", help="SDK folder name in the store")
    sp.add_argument("--board", default=DEFAULTS["board"])
    sp.add_argument("--source", default=".", help="app directory (default: cwd)")
    sp.add_argument("--build-dir", default="build")
    sp.add_argument("--pristine", action="store_true")
    sp.add_argument("extra", nargs="*", help="extra args for `west build`")
    sp.set_defaults(func=cmd_build, store_cmd=True)

    sp = sub.add_parser("shell", help="interactive shell with an SDK's environment")
    sp.add_argument("--sdk", default="")
    sp.set_defaults(func=cmd_shell, store_cmd=True, interactive=True)

    sp = sub.add_parser("flash", help="flash a built .hex from THIS machine (J-Link)")
    sp.add_argument("--hex", default="")
    sp.add_argument("--build-dir", default="build")
    sp.add_argument("--serial", default="", help="probe serial number")
    sp.add_argument("--core", default="Application")
    sp.add_argument("--nrfutil", default="")
    sp.set_defaults(func=cmd_flash, store_cmd=False)

    sp = sub.add_parser("build-image", help="build the ncs-base image + SDK volume")
    sp.set_defaults(func=cmd_build_image, store_cmd=False)

    return parser


def main():
    args = build_parser().parse_args()
    ctx = Ctx(args)

    if ctx.backend == "docker" and getattr(args, "store_cmd", False):
        sys.exit(delegate_to_docker(ctx, getattr(args, "interactive", False)))

    try:
        args.func(ctx)
    except subprocess.CalledProcessError as exc:
        die(f"command failed with exit code {exc.returncode}", exc.returncode or 1)
    except KeyboardInterrupt:
        die("interrupted", 130)


if __name__ == "__main__":
    main()
