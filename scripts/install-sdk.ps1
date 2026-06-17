# Install an nRF Connect SDK version (+ its matching toolchain) into the shared
# 'ncs-sdks' volume via nrfutil. Versions live side-by-side; install as many as
# you like. This is the only step that downloads an SDK, and it's per-version,
# not per-project.
#
#   ./scripts/install-sdk.ps1 -NcsRev v3.3.0
#   ./scripts/install-sdk.ps1 -NcsRev v3.2.4
#
# List what's available / installed:
#   ./scripts/install-sdk.ps1 -List
param(
    [string]$NcsRev = "v3.3.0",
    [string]$Image  = "ncs-base:latest",
    [string]$Volume = "ncs-sdks",
    [switch]$List
)

$ErrorActionPreference = "Stop"

if ($List) {
    docker run --rm -v "${Volume}:/opt/nordic/ncs" $Image bash -lc `
        "echo '=== available ==='; nrfutil sdk-manager search; echo; echo '=== installed ==='; nrfutil sdk-manager list"
    return
}

docker run --rm -v "${Volume}:/opt/nordic/ncs" $Image bash -lc `
    "nrfutil sdk-manager install $NcsRev --install-dir /opt/nordic/ncs"

Write-Host "`nInstalled NCS $NcsRev into volume '$Volume'." -ForegroundColor Green
