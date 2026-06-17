# Install a CUSTOM nRF/Zephyr SDK (your own manifest repo: a fork, a private
# repo, GitLab, a different manifest file, a pinned revision...) into the shared
# 'ncs-sdks' volume via `west` — NOT nrfutil sdk-manager. It lands at
# /root/ncs/<Name> alongside the official SDKs and is discovered by the
# extension the same way (ncs-register-sdks registers any west workspace).
#
# A custom SDK still needs a TOOLCHAIN to build. It reuses an already-installed
# nrfutil toolchain (-ToolchainVer); pick the NCS version your SDK is based on.
# Install that toolchain first if needed:  ./scripts/install-sdk.ps1 -NcsRev v3.3.0
#
#   # a fork / branch:
#   ./scripts/install-custom-sdk.ps1 -Name my-sdk -ManifestUrl https://github.com/me/sdk-nrf-fork -Rev my-branch
#   # a private repo with a non-default manifest file, based on v3.2.4 toolchain:
#   ./scripts/install-custom-sdk.ps1 -Name acme -ManifestUrl git@gitlab.com:acme/ncs.git -ManifestFile west-acme.yml -ToolchainVer v3.2.4
param(
    [Parameter(Mandatory)][string]$Name,
    [Parameter(Mandatory)][string]$ManifestUrl,
    [string]$Rev          = "",
    [string]$ManifestFile = "",
    [string]$ToolchainVer = "v3.3.0",
    [string]$Image        = "ncs-base:latest",
    [string]$Volume       = "ncs-sdks",
    [switch]$Blobs
)

$ErrorActionPreference = "Stop"
$dest = "/root/ncs/$Name"

# Build the `west init` argument list, adding optional flags only when given.
$initArgs = "-m `"$ManifestUrl`""
if ($Rev)          { $initArgs += " --mr `"$Rev`"" }
if ($ManifestFile) { $initArgs += " --mf `"$ManifestFile`"" }

$steps = @(
    "west init $initArgs `"$dest`"",
    "cd `"$dest`"",
    "west update"
)
if ($Blobs) { $steps += "west blobs fetch hal_nordic || true" }
$steps += "west zephyr-export"
$inner = $steps -join " && "

Write-Host "Installing custom SDK '$Name' from $ManifestUrl (toolchain env: $ToolchainVer)..." -ForegroundColor Cyan

docker run --rm `
    -v "${Volume}:/root/ncs" `
    $Image bash -lc "nrfutil toolchain-manager launch --ncs-version $ToolchainVer -- bash -c '$inner'"

Write-Host "`nInstalled custom SDK '$Name' into volume '$Volume' at $dest." -ForegroundColor Green
Write-Host "In the extension: Add build configuration -> SDK = '$Name', Toolchain = $ToolchainVer." -ForegroundColor Yellow
Write-Host "Headless build:   ./scripts/build.ps1 -Sdk $Name -NcsRev $ToolchainVer" -ForegroundColor Yellow
