# Build rimbrain.exe + its writable-side layout (UR-ARC-009).
# Usage: tools/build-exe.ps1  ->  dist/{rimbrain.exe,packs/,profiles/}
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
    # PyInstaller --noconfirm deletes the whole dist/rimbrain dir —
    # stash session state first, restore after the build.
    $dist = Join-Path $root "dist\rimbrain"
    $state = Join-Path $dist "state"
    $stash = Join-Path $env:TEMP ("rimbrain-state-" + [Guid]::NewGuid().ToString("N"))
    if (Test-Path $state) { Move-Item $state $stash }

    python -m PyInstaller --noconfirm --clean tools/rimbrain.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller exited $LASTEXITCODE" }

    # onedir layout: dist/rimbrain/{rimbrain.exe,_internal/}; writable
    # dirs live beside the exe, i.e. inside dist/rimbrain/
    $exe = Join-Path $dist "rimbrain.exe"
    if (-not (Test-Path $exe)) { throw "expected $exe" }

    # Writable/editable dirs next to the exe (never inside the bundle).
    # Mirror source CONTENTS into dest (Copy-Item <dir> <dest> nests when
    # dest exists), and drop top-level entries absent from source so stale
    # flat pack files and nested dirs can't shadow the current registry.
    function Sync-Dir($src, $dst, $preserve = @()) {
        New-Item -ItemType Directory -Force $dst | Out-Null
        $srcNames = @(Get-ChildItem $src -Name)
        Get-ChildItem $dst | Where-Object {
            $srcNames -notcontains $_.Name -and $preserve -notcontains $_.Name
        } | Remove-Item -Recurse -Force
        Copy-Item -Recurse -Force (Join-Path $src '*') $dst
    }

    Sync-Dir (Join-Path $root "components/rimbrain/packs") `
        (Join-Path $dist "packs") -preserve @('candidates')
    Sync-Dir (Join-Path $root "profiles") (Join-Path $dist "profiles")
    New-Item -ItemType Directory -Force $state | Out-Null
    Write-Host "OK: $exe"
    Write-Host "Run:  $exe run            # fair colonyrun1 + overlay"
    Write-Host "      $exe run --mode sim # sim smoke"
} finally {
    # restore stashed session state whether the build passed or failed
    if ($stash -and (Test-Path $stash)) {
        New-Item -ItemType Directory -Force $state | Out-Null
        Copy-Item -Recurse -Force (Join-Path $stash '*') $state
        Remove-Item -Recurse -Force $stash
    }
    Pop-Location
}
