# serve-laya.ps1 -- start the Laya System-1 decision server (rimbrain.select tier).
# Prereqs (one-time): laya.exe + ggmlc runtime + CUDA 12 pip wheels under J:\RimAgent\models\laya
#   pip wheels provide cudart64_12/cublas64_12; laya.exe needs them on PATH.
# Runs in foreground; API on http://127.0.0.1:8780 (GET /health, /v1/models, /v1/presets, POST /v1/systemone)
$layaDir = 'J:\RimAgent\models\laya'
$env:Path = "$layaDir\.venv\Lib\site-packages\nvidia\cuda_runtime\bin;$layaDir\.venv\Lib\site-packages\nvidia\cublas\bin;" + $env:Path
$model = Join-Path $layaDir 'laya_english_q8_0.gguf'
if (-not (Test-Path $model)) { throw "model missing: $model" }
& "$layaDir\laya.exe" serve $model --port 8780 --device auto --cuda-graph
