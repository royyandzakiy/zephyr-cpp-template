# Interactive shell in the build environment for a chosen SDK version, with this
# project mounted and ZEPHYR_BASE set so `west build` works from the project dir.
#
#   ./scripts/shell.ps1                 # v3.3.0
#   ./scripts/shell.ps1 -NcsRev v3.2.4
# then, inside:
#   west build -b nrf5340dk/nrf5340/cpuapp .
param(
    [string]$NcsRev = "v3.3.0",
    [string]$Image  = "ncs-base:latest",
    [string]$Volume = "ncs-sdks"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$name = Split-Path -Leaf $root
$dest = "/workspaces/$name"

$inner = "export ZEPHYR_BASE=/opt/nordic/ncs/$NcsRev/zephyr; cd $dest; exec bash"

docker run -it --rm `
    -v "${Volume}:/opt/nordic/ncs" `
    -v "${root}:${dest}" `
    $Image bash -lc "nrfutil toolchain-manager launch --ncs-version $NcsRev -- bash -c '$inner'"
