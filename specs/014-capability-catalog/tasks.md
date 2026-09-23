# Tasks: Capability Catalog (feature 014)

- [x] T167 Contracts: `capability-catalog.schema.json` (forbids policy fields), corpus valid/invalid examples, event-map/registry wiring if needed (FR-1202, SC-1204)
- [x] T168 `capability-catalog.yaml`: catalog_version, ~20 wiki-cited domains, `implemented` entries for all registry fns/selectors/templates, `gap` entries for unmapped baseline RPCs + known wiki mechanics (FR-1201)
- [x] T169 `tools/capability_audit.py`: baseline + `--live` diff, per-domain coverage, exit codes (FR-1203, SC-1201, SC-1203)
- [x] T170 Tests: schema validation, bidirectional registry↔catalog consistency, forbidden-key scan, audit smoke; suite/corpus/validators green; docs (README, INDEX, TRACEABILITY) (FR-1204/1205, SC-1202, SC-1204, SC-1205)
