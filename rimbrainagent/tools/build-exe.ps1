# Build rimbrain.exe + its writable-side layout (UR-ARC-009).
# Usage: tools/build-exe.ps1  ->  dist/rimbrain/{rimbrain.exe,packs/,profiles/}
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
    python -m PyInstaller --noconfirm --clean tools/rimbrain.spec

    $dist = Join-Path $root "dist"
    $exe = Join-Path $dist "rimbrain.exe"
    if (-not (Test-Path $exe)) { throw "expected $exe" }

    # Writable/editable dirs next to the exe (never inside the bundle).
    Copy-Item -Recurse -Force (Join-Path $root "components/rimbrain/packs") `
        (Join-Path $dist "packs")
    Copy-Item -Recurse -Force (Join-Path $root "profiles") `
        (Join-Path $dist "profiles")
    New-Item -ItemType Directory -Force (Join-Path $dist "state") | Out-Null

    Write-Host "OK: $exe"
    Write-Host "Run:  $exe run            # fair start-mode + overlay"
    Write-Host "      $exe run --mode sim # sim smoke"
} finally {
    Pop-Location
}
