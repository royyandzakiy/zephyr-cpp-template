# Flash the firmware built in the container, from the WINDOWS HOST.
# This is the reliable path on Windows: the J-Link drivers + `nrfutil device`
# run natively here, and the build output is in the bind-mounted build/ folder.
# (In-container flashing over WSL2/usbipd is flaky — see README §6.)
#
# Auto-picks build\merged.hex (sysbuild) else the app's zephyr.hex.
#
#   ./scripts/flash.ps1
#   ./scripts/flash.ps1 -SerialNumber 1050073602    # if multiple probes
#   ./scripts/flash.ps1 -Hex C:\path\to\firmware.hex
param(
    [string]$Hex          = "",
    [string]$SerialNumber = "",
    [string]$Core         = "Application",
    [string]$Nrfutil      = "C:\ncs\nrfutil.exe"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if (-not $Hex) {
    $merged = Join-Path $root "build\merged.hex"
    if (Test-Path $merged) {
        $Hex = $merged
    } else {
        $app = Get-ChildItem -Path (Join-Path $root "build") -Recurse -Filter "zephyr.hex" -ErrorAction SilentlyContinue |
               Select-Object -First 1
        if ($app) { $Hex = $app.FullName }
    }
}
if (-not $Hex -or -not (Test-Path $Hex)) {
    throw "No .hex found under build/. Build in the container first, then run this on the host."
}

Write-Host "Flashing $Hex (core: $Core)" -ForegroundColor Cyan
$pargs = @(
    "device", "program",
    "--firmware", $Hex,
    "--core", $Core,
    "--options", "chip_erase_mode=ERASE_RANGES_TOUCHED_BY_FIRMWARE,reset=RESET_SYSTEM"
)
if ($SerialNumber) { $pargs += @("--serial-number", $SerialNumber) }

& $Nrfutil @pargs
Write-Host "Done." -ForegroundColor Green
