# baseline-validate -- thin shim: python tools/baseline_validate.py
$root = Split-Path $PSScriptRoot -Parent
python (Join-Path $root 'tools\baseline_validate.py') @args
exit $LASTEXITCODE
