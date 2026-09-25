# setup-laya.ps1 -- one-time, idempotent install of the Laya System-1 decision server.
# Replicates the verified 2026-09-22 manual setup on this machine:
#   laya.exe + ggmlc-run.exe (ggmlc v0.9.2, cuda-sm89 binaries; sm89 JITs fine on RTX 5060 Ti sm_120)
#   laya_english_q8_0.gguf model (mys/laya-GGUF, 431MB)
#   CUDA 12 runtime/cuBLAS DLLs via pip wheels into a local .venv (no CUDA toolkit needed)
# Run tools/serve-laya.ps1 afterward to start the server on :8780.
param(
    [string]$Dir = 'J:\RimAgent\models\laya',
    [switch]$F16          # download the 807MB f16 model instead of q8_0
)
$ErrorActionPreference = 'Stop'
$env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')
$rel = 'https://github.com/monatis/ggmlc/releases/download/v0.9.2'
New-Item -ItemType Directory -Path $Dir -Force | Out-Null
Push-Location $Dir

if (-not (Test-Path 'laya.exe')) {
    Write-Host 'downloading laya binary...'
    Invoke-WebRequest "$rel/laya-windows-x86_64-cuda-sm89.zip" -OutFile laya-win.zip -TimeoutSec 300
    Expand-Archive laya-win.zip -DestinationPath . -Force
} else { Write-Host 'ok: laya.exe present' }

if (-not (Test-Path 'ggmlc-run.exe')) {
    Write-Host 'downloading ggmlc runtime...'
    Invoke-WebRequest "$rel/ggmlc-run-windows-x86_64-cuda-sm89.zip" -OutFile ggmlc-run.zip -TimeoutSec 300
    Expand-Archive ggmlc-run.zip -DestinationPath . -Force
} else { Write-Host 'ok: ggmlc-run.exe present' }

$gguf = if ($F16) { 'laya_english_f16.gguf' } else { 'laya_english_q8_0.gguf' }
if (-not (Test-Path $gguf)) {
    Write-Host "downloading $gguf (~430MB)..."
    Invoke-WebRequest "https://huggingface.co/mys/laya-GGUF/resolve/main/$gguf" -OutFile $gguf -TimeoutSec 900
} else { Write-Host "ok: $gguf present" }

if (-not (Test-Path '.venv\Scripts\python.exe')) {
    Write-Host 'creating venv (CUDA DLL host)...'
    uv venv .venv --python 3.13 --seed
}
# CUDA-12 runtime DLLs laya.exe links against (cudart64_12, cublas64_12) come from pip wheels.
& .\.venv\Scripts\pip install -q ggmlc==0.9.2 nvidia-cuda-runtime-cu12 nvidia-cublas-cu12

# verify: laya.exe info with CUDA bins on PATH
$env:Path = "$Dir\.venv\Lib\site-packages\nvidia\cuda_runtime\bin;$Dir\.venv\Lib\site-packages\nvidia\cublas\bin;" + $env:Path
& .\laya.exe info $gguf | Select-Object -First 5
if ($LASTEXITCODE -ne 0) { throw 'laya.exe info failed' }
Write-Host "`nsetup complete. Start with: .\tools\serve-laya.ps1  (API on http://127.0.0.1:8780)"
Pop-Location
