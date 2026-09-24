# Phase 1 Data Model: Guided Launcher UI

Entities from spec.md "Key Entities". UI-local state lives in memory;
persisted state reuses existing flat-file channels (no new evidence files).

## Launch Configuration

The parameter set assembled on the Setup screen; serialized into the loop
child's argv on GO. Immutable while a run is live.

| Field | Type | Source | Notes |
|---|---|---|---|
| mode | enum {sim, live, start, improve, combat, cycle} | radio | default `start`; shrinks under feature 017 |
| pack | pack id | radio list | default `start-mode-v0` |
| iterations | int ≥1 | spinbox | default 2000 |
| bridge | url string | text | default `http://127.0.0.1:8765` |
| fair | bool | check | default **on**; `--dev` inverts |
| live | bool | check | required by live-ish modes |
| live_brain | bool | check | default on |
| live_mutate | bool | check | default on; needs mode ∈ {start, live} |
| feed | bool | check | default on |
| ledger | bool | check | default off |
| no_store | bool | check | default off |
| no_hold | bool | check | default off; start mode only |

**Derived**: `argv() -> list[str]` — flag assembly, order-stable, tested
against `runtime loop` parsing. `violations() -> list[str]` — the
constraint mirror (research R6); empty ⇒ GO enabled.

**State**: `idle → running → stopped|exited`. `running` freezes argv-editing
controls; transitions driven by Run Handle.

## Pack Descriptor

A discoverable pack — read for the list, written by the editor.

| Field | Type | Source |
|---|---|---|
| id | string (dir name / flat stem) | `scan_packs` (existing) |
| path | file path | `packs/<id>/pack.yaml` or `<id>.yaml` |
| class | enum {fair, dev} | pack.yaml `class` (default fair) |
| pack_id | string | pack.yaml `pack_id` |
| derived_from | string? | pack.yaml `derived_from` (editor-set) |
| active | bool | `brain_status.json` `pack_id` match |

**Rules**: `class==dev` ⇒ unselectable while `fair` (FR-012). Id namespace:
`[a-z0-9-]` slug, unique under `packs/`; user packs never in `candidates/`.

## Brain Status

Per-role verification record, refreshed on demand and on screen open.

| Field | Type | Notes |
|---|---|---|
| role | string (`rimbrain.*`) | row identity |
| resolved | {endpoint_id, model, api} \| {kind: fallback, name} | `resolve_role` offline |
| verdict | enum {checking, answered, model_failed, unreachable, missing_secret, fallback_only, unbound} | from `probe_live` |
| latency_ms | float? | live call only |
| fallbacks | list[string] | role's `degraded_paths`, verbatim display |
| checked_utc | iso8601 | staleness marker |

**Rules**: verdict `answered` ⇒ green; `model_failed`/`unreachable`/
`missing_secret` ⇒ amber/red + fallback note; never blocks GO (FR-009).

## Guided Edit Session

A loaded pack doc + pending form edits; the unit of editor work.

| Field | Type | Notes |
|---|---|---|
| source_path | file path | read-only after load |
| doc | dict | `yaml.safe_load` result |
| dirty | bool | any form write |
| outline | tree | v0-path → label map (research R5) |
| save_name | string | default `<source>-custom`, slug-enforced |
| issues | list[string] | last validation result |

**Transitions**: `clean → dirty → validating → saved(new pack) | invalid`.
`saved` ⇒ rescan pack list + select new id. Overwrite-active is a separate
confirmed path (FR-024), not part of the normal flow.

## Run Handle

The supervised loop child — one per window.

| Field | Type | Notes |
|---|---|---|
| proc | subprocess.Popen | spawned on GO/Restart |
| argv | list[string] | displayed verbatim on Setup (diagnosis, Principle VII) |
| started_utc | iso8601 | |
| exit_code | int? | from `proc.poll()` each refresh |

**Transitions**: `none → running → exited(code)`. Window close with
`running` ⇒ terminate child first (FR-021).

## PARAM_SPEC (declarative flag table)

Not a runtime entity — the module-level table driving the grid (FR-002).

```text
{flag, label, kind: check|radio|spin|text|choice, default, group,
 hint, enable_when: {field, in|eq, value}, block_when: {field, in|eq, value}}
```

`enable_when` greys a control; `block_when` produces a Launch Configuration
violation. One row per loop flag; pack is a `choice` bound to Pack
Descriptors.
