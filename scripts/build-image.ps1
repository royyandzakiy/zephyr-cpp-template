# Build the shared nRF Connect SDK workspace image ONCE.
# Re-run only when you want to move to a newer SDK revision.
#
#   ./scripts/build-image.ps1                  # latest (main)
#   ./scripts/build-image.ps1 -NcsRev v2.9.0   # pinned release
param(
    [string]$NcsRev = "main",
    [string]$Tag    = "ncs-workspace:latest"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

docker build --build-arg NCS_REV=$NcsRev -t $Tag $root
Write-Host "`nBuilt $Tag (NCS_REV=$NcsRev)." -ForegroundColor Green
