# Phase 0 Research: Fork Bootstrap and Contract Foundation

**Date**: 2026-09-22 | **Plan**: [plan.md](plan.md)

All Technical Context items resolved — no NEEDS CLARIFICATION remains.

## R1 — Contract schema language and validator

**Decision**: JSON Schema 2020-12 as the authoritative contract format; Python `jsonschema` package
for validation; canonical JSON (JCS / RFC 8785) for deterministic hashing.

**Rationale**: `specs/20-submodules/CONTRACTS.md` already normatively declares JSON Schemas and
language-independent golden hash tests; JSON Schema is the only choice that serves Python, C#, and
TypeScript consumers without coupling them to one runtime's object model. `jsonschema` is mature,
draft-2020-12 compliant, and needs no code generation for C0–C1.

**Alternatives considered**: Pydantic models as source of truth (rejected — Python-only semantics,
would make contracts depend on implementation); YAML-schema DSLs (rejected — no standard validator
ecosystem); Protobuf/MessagePack (rejected — contracts must be human-readable per constitution V;
binary framing can layer later).

## R2 — Baseline capture without a live game

**Decision**: Baseline bundle v1 is built entirely offline — static extraction plus synthesized
samples — with live-captured samples marked as a deferred follow-up fixture.

Three capture sources:

1. **RPC inventory**: parse `[Rpc(name, doc)]` attributes in `upstream/rimagent/mod/Source` (97
   methods) and `mod-steward/Source` (18 methods) — no game required.
2. **Event corpus**: `bus.py`'s docstring defines the full upstream contract — 18 upstream bus kinds
   (`status`, `think_start`, `reasoning`, `assistant`, `tool_call`, `tool_result`, `think_end`,
   `ledger`, `watcher`, `brain_change`, `watchdog`, `episode_start`, `episode_end`, `situation`,
   `operator`, `reply`, `log`, `error`) on envelope `{seq, t, kind, data}`. Synthesized examples are
   generated per documented shapes and marked `provenance: synthesized-from-docstring`.
3. **Automation surface**: Steward orders/scorer/stock RPCs and config surface from
   `mod-steward/Source` + upstream AGENTS.md.

**Deviation noted**: real `state.summary`/event samples from a live upstream run land as baseline
bundle v1.1 when the first instrumented run executes (Phase 0 prerequisite is toolchains, not a game
session). Synthesized samples validate format, not values — flagged in the bundle manifest.

**Alternatives considered**: requiring a live upstream session before any contract work (rejected —
unnecessarily serializes Phase 0 behind a RimWorld install); copying samples from upstream docs only
(rejected — stale; static extraction is regenerable and diffable).

## R3 — Component bootstrap mechanics

**Decision**: components live as ordinary directories in the superproject now, each with a committed
validation entry point and CI shell; promotion to Git submodules happens only when portable remotes
exist.

**Rationale**: AGENTS.md forbids local filesystem URLs in `.gitmodules`, and no remotes exist yet.
This also matches constitution IV (a repo split needs independent release cadence + consumers) and
keeps WP-000 executable offline.

**Alternatives considered**: `git subtree` splits now (rejected — rewrites history expectations
before remotes exist); immediate submodule pointers to not-yet-created remotes (rejected —
unclonable).

## R4 — Fixture package format

**Decision**: directory package — `manifest.yaml` (provenance, schema revisions, content hashes),
`input.jsonl` (recorded inputs/events), `expected.jsonl` (observable outputs), optional `blobs/` for
content-addressed payloads. Rejected records are quarantined under `quarantine/`.

**Rationale**: matches DATA-OWNERSHIP flat-file rules, diffable in review, streamable, and aligns
with the export bundle layout (`specs/30-contracts/EVENT-AND-EXPORT.md` §5) so fixtures and exports
share tooling.

**Alternatives considered**: single-file archive (rejected — not diff-friendly); SQLite (rejected —
violates flat-file canonical-record rule).

## R5 — Upstream event → canonical envelope mapping

**Decision**: every upstream `kind` maps to a namespaced canonical `event_type`; the mapping table is
itself a contract artifact (`components/contracts/registry/event-map.yaml`, the event-type registry),
versioned alongside the envelope schema.

Mapping approach: `seq` → `sequence`; `t` → `wall_time_utc`; `kind` → `event_type` via registry
(e.g. `tool_call` → `model.tool_call` interim / `intent.*` post-dispatcher; `ledger` →
`bridge.event.ingested`; `episode_start/end` → `episode.started/closed`; `watchdog` →
`policy.watchdog.completed`). Fields with no upstream equivalent (`game_tick`, causality, revision
set) are emitted `null`/absent per the absent-null-unknown-censored rules — never fabricated.

**Alternatives considered**: renaming upstream kinds in place (rejected — `upstream/` is read-only);
dual-write inside upstream bus (rejected — same reason; mapping lives in the runtime adapter).

## R6 — Baseline integrity checking

**Decision**: validation compares `git submodule status` commits against the manifest pins AND runs a
porcelain-status scan of the upstream tree; modified/dirty content fails validation.

**Rationale**: submodule pin + `git status --porcelain` catches both wrong revision and in-tree edits
in < 60 s on this repo size — satisfies SC-006 without a full content hash pass. A full tree hash is
recorded in the bundle manifest for archival proof.

## Resolved unknowns summary

| # | Question | Resolution |
|---|----------|------------|
| R1 | Schema language | JSON Schema 2020-12 + `jsonschema` + JCS hashing |
| R2 | Baseline without game | Static `[Rpc]` extraction + docstring-synthesized event corpus; live samples deferred |
| R3 | Submodule timing | In-repo dirs → promote on remote creation |
| R4 | Fixture format | Directory package, YAML manifest, JSONL streams, hashed |
| R5 | Event mapping | Versioned `registry/event-map.yaml` contract artifact |
| R6 | Integrity check | Pin compare + porcelain scan; full hash in manifest |
