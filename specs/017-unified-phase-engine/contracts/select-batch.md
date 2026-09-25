# Contract: Select batch — action list → systemone questions

**Feature**: 017 | **Producer**: `select.py` | **Consumer**: `rimbrain.select` endpoint (Laya, systemone API)

## Request

One batched `systemone_decide` call per decide poll:

```json
{
  "state": "<phase_id>:<tick>",
  "model": "<bound model>",
  "questions": {
    "q.colony": {
      "type": "choice",
      "instructions": "<pack-rendered prompt fragment>",
      "criteria": {"<cand_id>": "<label + key stats>", "...": "..."},
      "context": {"colony": {...}, "plan": "<plan_id>", "efficiency": {...}}
    },
    "q.pawn.<pawn_id>": {
      "type": "choice",
      "criteria": {"<cand_id>": "<label>", "...": "..."},
      "context": {"pawn": {...stats...}}
    }
  }
}
```

Rules:
- `criteria` keys are candidate ids **from the compiled action list only** — the model can only name offered options.
- ≤20 candidates total across all questions (engine hard bound).
- One request per poll regardless of pawn count.
- `context` carries the stats inputs required by FR-1409 — no second RPC needed by the model.

## Response → application

```json
{"answers": {"q.colony": {"choice": "<cand_id>"}, "q.pawn.X": {"choice": "<cand_id>"}}}
```

Validation per answer, in order:

1. `choice` ∈ offered candidate ids → dispatch its `{template, params}` via the single writer → `DecisionRecord{applied: choice}`.
2. `choice` invalid/absent/malformed → pack-declared `fallback` candidate → `DecisionRecord{applied: fallback, fallback: true}` + `select.invalid` event.
3. Endpoint unreachable/error → `fallback` for every question → `select.degraded` event.
4. Shadow mode: model answer recorded (`shadow: true`) but fallback executes — no dispatch from the pick.

## Failure bounds

- Zero candidates → fallback path directly (no request issued).
- Request timeout → treated as endpoint-down; poll proceeds on fallback — decide NEVER blocks the loop.
- Every outcome emits a `decision`/`select.*` event (Constitution VII).
