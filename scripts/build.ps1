# One-shot build of this project inside the shared image (no interactive shell).
# Build artifacts land in ./build on the host (it's bind-mounted).
#
#   ./scripts/build.ps1
#   ./scripts/build.ps1 -Board nrf5340dk/nrf5340/cpuapp -Pristine
param(
    [string]$Board   = "nrf5340dk/nrf5340/cpuapp",
    [string]$Tag     = "ncs-workspace:latest",
    [switch]$Pristine
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$name = Split-Path -Leaf $root
$dest = "/workspace/projects/$name"
$pristineFlag = if ($Pristine) { "-p always" } else { "" }

docker run --rm `
    -v "${root}:${dest}" `
    -w $dest `
    $Tag bash -lc "west build -b $Board $pristineFlag ."

Write-Host "`nBuilt for $Board. Flash from the host: nrfutil device program --firmware build/zephyr/zephyr.hex" -ForegroundColor Green
