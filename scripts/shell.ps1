# Interactive shell in the build environment, with this project mounted and
# ZEPHYR_BASE set so `west build` works from the project dir. -NcsRev picks the
# TOOLCHAIN env; -Sdk picks which SDK folder to build against (defaults to
# -NcsRev). For a custom SDK: -Sdk my-sdk -NcsRev v3.3.0.
#
#   ./scripts/shell.ps1                          # v3.3.0
#   ./scripts/shell.ps1 -NcsRev v3.2.4
#   ./scripts/shell.ps1 -Sdk my-sdk -NcsRev v3.3.0
# then, inside:
#   west build -b nrf5340dk/nrf5340/cpuapp .
param(
    [string]$NcsRev = "v3.3.0",
    [string]$Sdk    = "",
    [string]$Image  = "ncs-base:latest",
    [string]$Volume = "ncs-sdks"
)

$ErrorActionPreference = "Stop"
if (-not $Sdk) { $Sdk = $NcsRev }
$root = Split-Path -Parent $PSScriptRoot
$name = Split-Path -Leaf $root
$dest = "/workspaces/$name"

$inner = "export ZEPHYR_BASE=/root/ncs/$Sdk/zephyr; cd $dest; exec bash"

docker run -it --rm `
    -v "${Volume}:/root/ncs" `
    -v "${root}:${dest}" `
    $Image bash -lc "nrfutil toolchain-manager launch --ncs-version $NcsRev -- bash -c '$inner'"
