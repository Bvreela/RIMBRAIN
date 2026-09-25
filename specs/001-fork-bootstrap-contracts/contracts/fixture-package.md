# Contract: Replay Fixture Package

**Version**: 0.1.0-draft | **Implements**: FR-010, FR-011 | **Owner**: `components/contracts` (schema) + `components/lab` (replayer, later)

## Package layout

```text
fix.<slug>/
├── manifest.yaml        # provenance + integrity
├── input.jsonl          # canonical records fed to replay
├── expected.jsonl       # observable outputs to compare
├── blobs/               # optional content-addressed payloads
└── quarantine/          # torn/invalid records separated at load
```

## `manifest.yaml` required fields

- `schema_version`, `fixture_id` (`fix.*`), `created_utc`
- `provenance`: `{ source: baseline-bundle|live-run|synthesized, source_hash, episode_id?, notes }`
- `schema_pins`: contract/schema revisions the fixture was recorded under
- `files`: `{path: sha256}` for every member file
- `expected_comparison`: `{ mode: exact|field-subset, tolerance?: {...} }`

## Harness semantics

1. Load manifest → verify file hashes → parse `input.jsonl` into CanonicalRecords.
2. Torn tail / hash mismatch / missing provenance → **fail closed**, naming the defect (FR-011);
   salvageable trailing garbage moves to `quarantine/`, intact prefix still loads (FR-012 analog).
3. Replay feeds inputs through the system under test offline — no game, bridge, model, or network.
4. Compare observed outputs to `expected.jsonl` under `expected_comparison.mode`.
5. Report: per-line equivalent/divergent with record IDs; identical report on repeat runs (SC-005).

## Validation corpus

Valid: minimal single-record fixture; maximal with blobs.
Invalid: missing provenance, hash mismatch, truncated JSONL tail, `fixture_id` violating ID grammar,
unknown `schema_version`.
