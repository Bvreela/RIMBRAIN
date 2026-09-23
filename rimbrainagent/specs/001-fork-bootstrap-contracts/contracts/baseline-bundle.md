# Contract: Upstream Baseline Bundle

**Version**: 0.1.0-draft | **Implements**: FR-002, FR-009, SC-006 | **Owner**: superproject tooling → `baselines/`

## Purpose

Immutable characterization of the pinned upstream fork baseline. It is the "before" picture every
migration equivalence claim diffs against.

## Bundle layout

```text
baselines/upstream-85cb050/
├── MANIFEST.yaml
├── rpc-inventory.json        # 115 methods: 97 RimBridge + 18 Steward, from [Rpc] attributes
├── event-corpus/
│   └── bus-kinds.jsonl       # one synthesized record per upstream kind, provenance-marked
├── automation-surface.yaml   # Steward orders/scorer/stock RPC + config surface
├── tree-hash.sha256          # full upstream tree content hash
└── gaps.yaml                 # deferred items (live state.summary/event samples) + reason
```

## `MANIFEST.yaml` required fields

- `schema_version`, `bundle_id` (`blb.*`), `created_utc`, `tool_manifest` (OS + tool versions)
- `pins`: upstream commit `85cb050dec47691f2a80096fdc8c8a8e2051bb13`, nested RimBridge
  `3c1e4c7cee151104b85bf9c8372e113f91c5f08d`
- `tree_hash` algorithm + value
- `capture_methods`: which fields are `static-extraction` vs `synthesized` vs `live-captured`
- `sealed`: bool — sealed bundles are immutable; corrections ship a new bundle version

## Integrity validation (runs on every validate job)

1. `git submodule status` commits == manifest pins.
2. `git status --porcelain` inside `upstream/rimagent` must be empty.
3. Optional deep mode recomputes `tree-hash.sha256`.

Any failure → baseline-integrity error via `common/error` envelope.

## Deferred capture (recorded in `gaps.yaml`)

- Live `state.summary`, `/events`, screenshot metadata, and real `run-*.jsonl` — require one
  instrumented upstream session; not a blocker for this feature (spec assumption).
