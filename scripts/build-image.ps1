# Build the small, version-agnostic ncs-base image and ensure the shared SDK
# volume exists. Run this ONCE per machine (re-run only to update host tools).
#
#   ./scripts/build-image.ps1
param(
    [string]$Image  = "ncs-base:latest",
    [string]$Volume = "ncs-sdks"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

docker build -t $Image $root
docker volume create $Volume | Out-Null

Write-Host "`nBuilt $Image and ensured volume '$Volume'." -ForegroundColor Green
Write-Host "Next: install an SDK version  ->  ./scripts/install-sdk.ps1 -NcsRev v3.3.0" -ForegroundColor Yellow
