# Headless build of THIS project against a chosen SDK version in the shared
# volume. Pick the version with -NcsRev; artifacts land in ./build on the host.
#
#   ./scripts/build.ps1                                   # v3.3.0, nRF5340 DK
#   ./scripts/build.ps1 -NcsRev v3.2.4
#   ./scripts/build.ps1 -Board nrf52840dk/nrf52840 -Pristine
param(
    [string]$NcsRev  = "v3.3.0",
    [string]$Board   = "nrf5340dk/nrf5340/cpuapp",
    [string]$Image   = "ncs-base:latest",
    [string]$Volume  = "ncs-sdks",
    [switch]$Pristine
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$name = Split-Path -Leaf $root
$dest = "/workspaces/$name"
$p    = if ($Pristine) { "-p always" } else { "" }

# Launch sets up the toolchain env; ZEPHYR_BASE selects which SDK to build against.
$inner = "export ZEPHYR_BASE=/root/ncs/$NcsRev/zephyr; " +
         "west build -b $Board $dest --build-dir $dest/build $p"

docker run --rm `
    -v "${Volume}:/root/ncs" `
    -v "${root}:${dest}" `
    $Image bash -lc "nrfutil toolchain-manager launch --ncs-version $NcsRev -- bash -c '$inner'"

Write-Host "`nBuilt $name for $Board with NCS $NcsRev." -ForegroundColor Green
Write-Host "Flash from the host: nrfutil device program --firmware build/$name/zephyr/zephyr.hex" -ForegroundColor Yellow
