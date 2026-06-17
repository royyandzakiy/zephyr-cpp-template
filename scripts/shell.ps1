# Open a shell in the shared workspace image with THIS project mounted into
# /workspace/projects/<folder-name>. The SDK comes from the image; only your
# source is mounted, so nothing is re-downloaded.
#
#   ./scripts/shell.ps1
# then, inside the container:
#   west build -b nrf5340dk/nrf5340/cpuapp .
param(
    [string]$Tag = "ncs-workspace:latest"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$name = Split-Path -Leaf $root
$dest = "/workspace/projects/$name"

docker run -it --rm `
    -v "${root}:${dest}" `
    -w $dest `
    $Tag bash
