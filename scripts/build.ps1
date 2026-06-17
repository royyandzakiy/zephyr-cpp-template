# Headless build of THIS project against a chosen SDK in the shared volume.
# -NcsRev picks the TOOLCHAIN env; -Sdk picks which SDK folder to build against
# (defaults to -NcsRev). For a custom SDK, set -Sdk to its folder name and
# -NcsRev to the toolchain it's based on. Artifacts land in ./build on the host.
#
#   ./scripts/build.ps1                                   # v3.3.0, nRF5340 DK
#   ./scripts/build.ps1 -NcsRev v3.2.4
#   ./scripts/build.ps1 -Sdk my-sdk -NcsRev v3.3.0        # custom SDK, v3.3.0 toolchain
#   ./scripts/build.ps1 -Board nrf52840dk/nrf52840 -Pristine
param(
    [string]$NcsRev  = "v3.3.0",
    [string]$Sdk     = "",
    [string]$Board   = "nrf5340dk/nrf5340/cpuapp",
    [string]$Image   = "ncs-base:latest",
    [string]$Volume  = "ncs-sdks",
    [switch]$Pristine
)

$ErrorActionPreference = "Stop"
if (-not $Sdk) { $Sdk = $NcsRev }   # default: SDK folder == toolchain version
$root = Split-Path -Parent $PSScriptRoot
$name = Split-Path -Leaf $root
$dest = "/workspaces/$name"
$p    = if ($Pristine) { "-p always" } else { "" }

# Launch sets up the toolchain env (-NcsRev); ZEPHYR_BASE selects which SDK
# folder to build against (-Sdk), so a custom SDK builds with a base toolchain.
$inner = "export ZEPHYR_BASE=/root/ncs/$Sdk/zephyr; " +
         "west build -b $Board $dest --build-dir $dest/build $p"

docker run --rm `
    -v "${Volume}:/root/ncs" `
    -v "${root}:${dest}" `
    $Image bash -lc "nrfutil toolchain-manager launch --ncs-version $NcsRev -- bash -c '$inner'"

Write-Host "`nBuilt $name for $Board (SDK=$Sdk, toolchain=$NcsRev)." -ForegroundColor Green
Write-Host "Flash from the host: nrfutil device program --firmware build/$name/zephyr/zephyr.hex" -ForegroundColor Yellow
