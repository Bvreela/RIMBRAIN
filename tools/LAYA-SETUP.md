# Laya decision server — Windows setup

Laya ([mys/laya-GGUF](https://huggingface.co/mys/laya-GGUF)) is the local **System-1 typed-decision
model** for `rimbrain.select` — the fast action-matrix tier. It is *not* a chat LLM: given a `state`
object plus named typed questions (`choice` / `score` / `noul`), it returns calibrated probabilities
in a single encoder pass. No tokens are generated; no OpenAI API is involved.

Verified reference numbers (RTX 5060 Ti, CUDA, `laya_english_q8_0.gguf`):

- ~55 ms for a 4-question batch (warm); ~9 s first call after boot (CUDA graph compile — one-time)
- Model: ModernBERT-large, 421 M params, 512-token context, English only
- API: `POST /v1/systemone`, `GET /health`, `GET /v1/models`, `GET /v1/presets`, plus a Decision
  Studio UI at `GET /`

## Quick setup

```powershell
.\tools\setup-laya.ps1            # downloads binary + model + CUDA DLLs (idempotent)
.\tools\serve-laya.ps1            # starts the server on http://127.0.0.1:8780
.\tools\dev.ps1 -StartLaya        # or have the dev loop start it on demand
```

Default install dir: `J:\RimAgent\models\laya` — override with `.\tools\setup-laya.ps1 -Dir D:\path`.
`-F16` fetches the 807 MB full-precision model instead of the default 431 MB Q8_0.

## What setup-laya.ps1 does (manual equivalent)

1. Download `laya-windows-x86_64-cuda-sm89.zip` and `ggmlc-run-windows-x86_64-cuda-sm89.zip` from
   [ggmlc releases](https://github.com/monatis/ggmlc/releases) (v0.9.2) and extract into the model dir.
2. Download the GGUF from Hugging Face:
   `https://huggingface.co/mys/laya-GGUF/resolve/main/laya_english_q8_0.gguf`
   (alternatives: `laya_english_f16.gguf`, `laya_english_ud_q4_k_m.gguf`; multilingual/typed families
   exist under `mys/laya-multilingual-GGUF` and `mys/laya-typed-decisions-GGUF`).
3. Create a `.venv` and install `ggmlc==0.9.2` **plus the NVIDIA CUDA-12 runtime wheels**
   (`nvidia-cuda-runtime-cu12`, `nvidia-cublas-cu12`). This is the non-obvious step — see below.
4. Verify with `laya.exe info <model>.gguf`.

## The CUDA DLL gotcha (the part that bites)

`laya.exe` links `cudart64_12.dll` and `cublas64_12.dll` but the release zips do **not** ship them —
the binary exits with `0xC0000135` (STATUS_DLL_NOT_FOUND) and no output. You do *not* need the full
CUDA Toolkit: the pip wheels provide the DLLs. `serve-laya.ps1` puts the wheel `bin/` dirs on `PATH`
before launching:

```powershell
$env:Path = "$dir\.venv\Lib\site-packages\nvidia\cuda_runtime\bin;" +
            "$dir\.venv\Lib\site-packages\nvidia\cublas\bin;" + $env:Path
```

`nvcuda.dll` itself ships with the NVIDIA driver — `nvidia-smi` working means it is present.

GPU notes: the `cuda-sm89` binary is built for Ada (RTX 40xx) but runs fine on Blackwell
(RTX 50xx, compute capability 12.0) via JIT. If CUDA init still fails, `--device cpu` works — a
421 M encoder is fast on CPU too (tens of ms per decision).

## Using the API

```powershell
$body = @{
  state     = @{ situation = '4 colonists, food for 2 days, raid warning, one injured.' }
  questions = @{
    danger = @{ type = 'noul'; instructions = 'Is the colony in immediate danger?' }
  }
} | ConvertTo-Json -Depth 8
Invoke-RestMethod -Uri 'http://127.0.0.1:8780/v1/systemone' -Method Post -Body $body -ContentType 'application/json'
```

Response: per-question `answers` with `choice`/`score`/`noul` result, `probabilities`, `confidence`,
and `usage.latency_ms`. `GET /v1/presets` lists built-in question bundles — `harness` is the
act / tool / ask_user / stop agent gate.

## Repo integration points

- `profiles/endpoints.yaml` — entry `local-laya` (`api: systemone`, `capabilities: [typed_decisions]`); hosted fallback `openrouter-decisions` uses the same wire shape via `/api/alpha/decisions`
- `profiles/bindings.yaml` — `rimbrain.select` binds here
- `tools/env-check.ps1` — port 8780 probe
- `tools/dev.ps1` — `laya decision server` step; `-StartLaya` auto-starts
- `specs/50-verification/E2E-TEST-ENVIRONMENT.md` — TE-073..075

## Limitations

- English-only checkpoint (use `laya-multilingual-GGUF` otherwise)
- 512-token context — keep `state` packets short; this is a selector, not a planner
- Not OpenAI-compatible — the runtime needs a `laya-systemone` adapter (spec 002 FR-011 family)
- Optional bearer auth via `LAYA_API_KEY`/`TYPESAFE_API_KEY` env vars if you want the port gated
