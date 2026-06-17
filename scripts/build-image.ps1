# Build the shared nRF Connect SDK workspace image ONCE.
# Re-run only when you want to move to a newer SDK revision.
#
#   ./scripts/build-image.ps1                  # v3.3.0 (matches reference)
#   ./scripts/build-image.ps1 -NcsRev main     # bleeding edge
param(
    [string]$NcsRev = "v3.3.0",
    [string]$Tag    = "ncs-workspace:latest"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

docker build --build-arg NCS_REV=$NcsRev -t $Tag $root
Write-Host "`nBuilt $Tag (NCS_REV=$NcsRev)." -ForegroundColor Green
