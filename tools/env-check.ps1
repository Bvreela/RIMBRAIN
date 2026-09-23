# env-check.ps1 — verify this machine's toolchain and game environment for RimBrainAgent dev.
# Reality-tested on this Windows box: git/devin are NOT on PATH, Developer Mode is off,
# game lives on V:\SteamLibrary, GABP bridge is the live one (5174), HTTP bridge (8765) is pending deploy.
# Refresh PATH first: winget-installed tools (uv) land on user PATH after this shell started.
$env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')
$results = @()
function Check($name, $ok, $detail = '', $fatal = $false) {
    $script:results += [pscustomobject]@{ Check = $name; Ok = [bool]$ok; Detail = $detail; Fatal = $fatal }
    $mark = if ($ok) { 'PASS' } elseif ($fatal) { 'FAIL' } else { 'WARN' }
    Write-Host "  [$mark] $name$(if ($detail) { " - $detail" })"
}

Write-Host '== toolchain =='
$git = Get-Command git -ErrorAction SilentlyContinue
$gitExe = if ($git) { 'git' } elseif (Test-Path 'C:\Program Files\Git\cmd\git.exe') { 'C:\Program Files\Git\cmd\git.exe' } else { $null }
Check 'git' ($null -ne $gitExe) $(if ($git) { 'on PATH' } elseif ($gitExe) { 'works via full path — NOT on PATH (scripts must use fallback)' } else { 'missing' }) ($null -eq $gitExe)
if ($gitExe) {
    $id = & $gitExe config --global user.email 2>$null
    Check 'git identity' ([bool]$id) $(if ($id) { $id } else { 'no global user.email — commit-producing tests need GIT_AUTHOR_*/GIT_COMMITTER_* env vars' })
}
$uvv = (& { uv --version 2>$null }); Check 'uv' ([bool]$uvv) $uvv ($true -eq $true -and -not $uvv)
$dnv = (& { dotnet --version 2>$null }); Check 'dotnet SDK' ([bool]$dnv) $dnv ($true -eq $true -and -not $dnv)
$pyv = (& { python --version 2>$null }); Check 'python' ([bool]$pyv) $pyv ($true -eq $true -and -not $pyv)
$dv = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock' -Name AllowDevelopmentWithoutDevLicense -ErrorAction SilentlyContinue).AllowDevelopmentWithoutDevLicense
Check 'Developer Mode' ($dv -eq 1) $(if ($dv -eq 1) { 'on' } else { 'off — symlinks need admin; use junctions for mod deploy; upstream symlink test will fail (WinError 1314)' })

Write-Host '== game =='
$steam = Get-Process steam -ErrorAction SilentlyContinue
Check 'Steam running' ([bool]$steam)
$rw = Get-Process RimWorldWin64 -ErrorAction SilentlyContinue
Check 'RimWorld running' ([bool]$rw) $(if ($rw) { (Get-Process RimWorldWin64).Path } else { 'not running' })
$mods = 'V:\SteamLibrary\steamapps\common\RimWorld\Mods'
Check 'Mods dir' (Test-Path $mods) $mods
$mcfg = "$env:USERPROFILE\AppData\LocalLow\Ludeon Studios\RimWorld by Ludeon Studios\Config\ModsConfig.xml"
if (Test-Path $mcfg) {
    $cfg = Get-Content $mcfg -Raw
    Check 'zorrobyte.rimbridge enabled' ($cfg -match 'zorrobyte\.rimbridge') $(if ($cfg -match 'zorrobyte\.rimbridge') { 'yes' } else { 'NOT in activeMods — deploy+enable before :8765 works' })
    Check 'brrainz.rimbridgeserver enabled' ($cfg -match 'brrainz\.rimbridgeserver')
} else { Check 'ModsConfig.xml' $false $mcfg }

Write-Host '== bridges =='
foreach ($p in @(8765, 5174, 8780)) {
    $up = [bool](Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue)
    Check "port $p listening" $up $(if ($p -eq 8765) { 'zorrobyte HTTP bridge' } elseif ($p -eq 5174) { 'pardeike GABP bridge' } else { 'Laya System-1 decisions' })
}
$plog = "$env:USERPROFILE\AppData\LocalLow\Ludeon Studios\RimWorld by Ludeon Studios\Player.log"
$tok = if (Test-Path $plog) { (Select-String -Path $plog -Pattern 'Bridge token:\s*([0-9a-fA-F]{16,})' | Select-Object -Last 1).Matches.Groups[1].Value } else { $null }
Check 'GABP token available' ([bool]$tok) $(if ($tok) { 'parsed from Player.log' } else { 'not found — pass --token to bridge_check.py' })

Write-Host '== repo =='
if ($gitExe) {
    $pins = & $gitExe -C "$PSScriptRoot\.." submodule status --recursive 2>$null
    Check 'submodule pins' ([bool]$pins) (($pins | ForEach-Object { $_.Trim() }) -join ' | ')
}
$fail = $results | Where-Object { -not $_.Ok -and $_.Fatal }
Write-Host ("`n{0}/{1} checks pass{2}" -f ($results | Where-Object Ok).Count, $results.Count, $(if ($fail) { " - FATAL: $($fail.Check -join ', ')" } else { '' }))
exit $(if ($fail) { 1 } else { 0 })
