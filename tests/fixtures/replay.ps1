# replay -- fixture replay gate (US-5, SC-005): deterministic, fail-closed.
# Usage: tests/fixtures/replay.ps1 fix.seed-001 [-Times 5] [-Mode exact]
param([Parameter(Mandatory=$true)][string]$Fixture, [int]$Times = 1, [string]$Mode = 'exact')
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')
Push-Location $root
$dir = Join-Path $PSScriptRoot $Fixture
$env:PYTHONPATH = "$root\components\lab\src;$root\components\contracts\src"
uv run --with pyyaml,jsonschema python -m lab.fixtures $dir --mode $Mode --report "$env:TEMP\replay-report.json"
$rc = $LASTEXITCODE
if ($rc -eq 0 -and $Times -gt 1) {
    $h0 = (Get-FileHash "$env:TEMP\replay-report.json" -Algorithm SHA256).Hash
    for ($i = 2; $i -le $Times; $i++) {
        uv run --with pyyaml,jsonschema python -m lab.fixtures $dir --mode $Mode --report "$env:TEMP\replay-report.json" | Out-Null
        if ((Get-FileHash "$env:TEMP\replay-report.json" -Algorithm SHA256).Hash -ne $h0) { Write-Host "FAIL: report diverged on run $i"; $rc = 1; break }
    }
    if ($rc -eq 0) { Write-Host "determinism: $Times identical reports" }
}
Pop-Location
exit $rc
