# deploy-mods.ps1 -- link built zorrobyte mods into the game's Mods dir and enable them.
# Junctions (not symlinks): no admin needed, survives without Developer Mode.
# Game must restart to load DLLs; this script does NOT restart (deferred per user choice).
#
# CAVEAT: RimWorld rewrites ModsConfig.xml on normal quit from its in-memory list, which
# predates this edit. If you quit/relaunch after deploying, re-run this script (idempotent),
# or toggle the mods in the in-game mod menu instead.
$ErrorActionPreference = 'Stop'
$root = Resolve-Path "$PSScriptRoot\..\upstream\rimagent"
$modsDir = 'V:\SteamLibrary\steamapps\common\RimWorld\Mods'
$map = [ordered]@{ 'RimBridge' = "$root\mod"; 'RimBridgeSteward' = "$root\mod-steward" }

foreach ($name in $map.Keys) {
    $link = Join-Path $modsDir $name
    $target = $map[$name]
    foreach ($dll in @("$target\1.6\Assemblies\$name.dll")) {
        if (-not (Test-Path $dll)) { throw "build first: missing $dll (run tools/build-mods.ps1)" }
    }
    if (Test-Path $link) {
        $item = Get-Item $link -Force
        if ($item.LinkType -eq 'Junction' -and $item.Target -eq $target) { Write-Host "ok: $name junction already -> $target"; continue }
        throw "$link exists and is not our junction -- remove it manually first"
    }
    New-Item -ItemType Junction -Path $link -Target $target | Out-Null
    Write-Host "linked: $name -> $target"
}

$mcfg = "$env:USERPROFILE\AppData\LocalLow\Ludeon Studios\RimWorld by Ludeon Studios\Config\ModsConfig.xml"
$xml = Get-Content $mcfg -Raw
foreach ($pkg in 'zorrobyte.rimbridge', 'zorrobyte.rimbridgesteward') {
    if ($xml -notmatch "<li>\s*$([regex]::Escape($pkg))\s*</li>") {
        $xml = $xml -replace '</activeMods>', "    <li>$pkg</li>`n  </activeMods>"
        Write-Host "enabled: $pkg (appended to activeMods)"
    } else { Write-Host "ok: $pkg already in activeMods" }
}
Set-Content $mcfg $xml -NoNewline

Write-Host @"
done. Restart RimWorld via Steam when ready (steam://rungameid/294100).
WARNING: quitting the running session rewrites ModsConfig from memory -- re-run this script
after quit if the zorrobyte mods show as disabled. Verify after restart:
  python tools/bridgecheck/bridge_check.py   # :8765 checks should pass
"@ -ForegroundColor Yellow
