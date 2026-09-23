# dev.ps1 - single entry point for the local dev loop on this machine.
#   .\tools\dev.ps1          # fast loop: env, submodules, corpus, baseline, bridge
#   .\tools\dev.ps1 -Full    # + upstream parity suites (pytest + dotnet test), slower
# Exit code 0 = all executed steps green; SKIP doesn't fail.
param([switch]$Full, [switch]$StartLaya)
$env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')
$repo = Resolve-Path "$PSScriptRoot\.."
$git = if (Get-Command git -ErrorAction SilentlyContinue) { 'git' } else { 'C:\Program Files\Git\cmd\git.exe' }
$failed = @(); $steps = @()

function Step($name, [scriptblock]$run, $skip = $false, $skipWhy = '') {
    if ($skip) { $script:steps += "SKIP $name ($skipWhy)"; Write-Host "  [SKIP] $name - $skipWhy"; return }
    Write-Host "`n== $name =="
    $ok = $false
    try { $ok = [bool](& $run) } catch { Write-Host "  error: $_" }
    if ($ok) { $script:steps += "PASS $name"; Write-Host "  [PASS] $name" }
    else { $script:steps += "FAIL $name"; $script:failed += $name; Write-Host "  [FAIL] $name" }
}

Step 'env-check' { & "$PSScriptRoot\env-check.ps1"; $LASTEXITCODE -eq 0 }

Step 'submodules' {
    & $git -C $repo submodule update --init --recursive | Out-Null
    $status = & $git -C $repo submodule status --recursive
    $status | ForEach-Object { Write-Host "  $_" }
    -not ($status | Select-String '^\-')
}

if ($Full) {
    Step 'upstream pytest' { Push-Location "$repo\upstream\rimagent\agent"; uv run pytest -q; $c = $LASTEXITCODE; Pop-Location; $c -eq 0 }
    Step 'dotnet mod tests' { dotnet test "$repo\upstream\rimagent\mod\Tests" --nologo -v quiet; $LASTEXITCODE -eq 0 }
    Step 'dotnet steward tests' { dotnet test "$repo\upstream\rimagent\mod-steward\Tests" --nologo -v quiet; $LASTEXITCODE -eq 0 }
}

Step 'contract corpus' { python "$repo\tests\contract\corpus_runner.py"; $LASTEXITCODE -eq 0 } `
    -skip (-not (Test-Path "$repo\tests\contract\corpus_runner.py")) -skipWhy 'T007 not implemented yet'

Step 'baseline integrity' { python "$PSScriptRoot\baseline_validate.py"; $LASTEXITCODE -eq 0 } `
    -skip (-not (Test-Path "$PSScriptRoot\baseline_validate.py")) -skipWhy 'T008 not implemented yet'

Step 'laya decision server' {
    $up = [bool](Get-NetTCPConnection -State Listen -LocalPort 8780 -ErrorAction SilentlyContinue)
    if (-not $up -and $StartLaya) {
        Start-Process powershell -ArgumentList '-NoProfile','-File',"$PSScriptRoot\serve-laya.ps1" -WindowStyle Hidden
        for ($i = 0; $i -lt 30 -and -not $up; $i++) { Start-Sleep 1; $up = [bool](Get-NetTCPConnection -State Listen -LocalPort 8780 -ErrorAction SilentlyContinue) }
    }
    if ($up) { (Invoke-RestMethod 'http://127.0.0.1:8780/health' -TimeoutSec 5).status -eq 'ok' } else { Write-Host '  not running - start via tools/serve-laya.ps1 or -StartLaya'; $false }
} -skip (-not (Test-Path 'J:\RimAgent\models\laya\laya.exe')) -skipWhy 'Laya not installed - run tools/setup-laya.ps1'

Step 'bridge check' { python "$PSScriptRoot\bridgecheck\bridge_check.py"; $LASTEXITCODE -eq 0 }

Write-Host "`n===== dev loop ====="; $steps | ForEach-Object { Write-Host "  $_" }
exit $(if ($failed) { 1 } else { 0 })
