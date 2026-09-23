# baseline-capture -- thin shim: python tools/baseline_capture.py [mode]
param([string]$Mode = 'all')
$root = Split-Path $PSScriptRoot -Parent
python (Join-Path $root 'tools\baseline_capture.py') $Mode @args
exit $LASTEXITCODE
