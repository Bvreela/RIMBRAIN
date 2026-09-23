# build-mods.ps1 — Windows build for RimBridge + Steward against the pinned upstream source.
# Verified 2026-09-22 with .NET SDK 10.0.401 (mods target net48; tests net10.0).
# Order matters: mod-steward references mod/1.6/Assemblies/RimBridge.dll — build mod first.
$ErrorActionPreference = 'Stop'
$root = Resolve-Path "$PSScriptRoot\..\upstream\rimagent"
$env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')

dotnet build "$root\mod\Source\RimBridge.csproj" -c Release --nologo -v quiet
if (-not (Test-Path "$root\mod\1.6\Assemblies\RimBridge.dll")) { throw 'RimBridge.dll missing' }

dotnet build "$root\mod-steward\Source\RimBridgeSteward.csproj" -c Release --nologo -v quiet
if (-not (Test-Path "$root\mod-steward\1.6\Assemblies\RimBridgeSteward.dll")) { throw 'RimBridgeSteward.dll missing' }

Write-Host "built: $root\mod\1.6\Assemblies\RimBridge.dll"
Write-Host "built: $root\mod-steward\1.6\Assemblies\RimBridgeSteward.dll"
Write-Host 'NOTE: game must restart to load new DLLs; deploy = junction Mods\RimBridge -> upstream\rimagent\mod (no admin needed)'
