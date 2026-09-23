# Implementation Plan: Capability Catalog (feature 014)

## Approach

1. **Schema (FR-1202)** — `components/contracts/schemas/rimbrain/capability-catalog.schema.json`: `{catalog_version, domains[], entries[]}`; entries `{id, kind, bridge_methods[], domains[], status, sources[], notes}` with `additionalProperties: false` (forbids policy fields by construction). Corpus: one valid + two invalid (policy field present; bad status).
2. **Catalog seed (FR-1201)** — `components/rimbrain/capability-catalog.yaml`:
   - `implemented` entries for every `policy.FNS`/`SELECTORS` member and every `templates` registry id, grouped by domain, citing wiki roots.
   - `gap` entries for baseline RPC methods with no primitive yet (e.g. `state.research`, `ui.trade`, `dev.weather` semantics as agent capabilities) and wiki-documented mechanics not yet bridged.
   - `domains` list (~20) each with a wiki root URL.
3. **Audit tool (FR-1203)** — `tools/capability_audit.py`: loads catalog + `baselines/upstream-85cb050/rpc-inventory.json` (or live `bridge.methods` with `--live`); reports unmapped methods, gap entries, per-domain coverage table; exit codes per FR-1203.
4. **Consistency gate (FR-1204)** — `tests/test_capability_catalog.py`: catalog validates against schema; every `implemented` entry resolves in `policy.FNS`/`SELECTORS`/`templates.TEMPLATES`; every registry member catalogued; no forbidden keys anywhere.

## Design notes

- Catalog is RimBrain data (validated, community-editable) — not consulted at runtime (FR-1205).
- `gap` is honest inventory, not failure: audit fails only on *uncatalogued* surface.
- Wiki sources are citation URLs on entries/domains, not scraped content — keeps the repo free of third-party text.

## Tasks

See `tasks.md` (T167–T170).
