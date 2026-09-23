# RimBridge integration submodule specification

**Status:** READY  
**Future path:** `integrations/rimbridge`  
**Remote:** prefer upstream `zorrobyte/rimbridge`  
**Reviewed revision:** `3c1e4c7`

## 1. Purpose

RimBridge is the generic loopback player-parity interface to RimWorld. RimBrainAgent consumes it as a pinned external dependency and avoids forking it unless a required generic observation/action cannot be implemented through current RPCs or add-on hooks.

## 2. Current contract

- HTTP loopback server.
- `POST /rpc` with method/params and `ok/result/error` envelope.
- health, method discovery, events, and screenshot endpoints.
- main-thread queue for Verse access.
- approximately 96 RPCs across game, state, map, UI, engine, definitions, development, and anchors.
- assembly RPC registration and extension hooks.

## 3. Integration rules

- Runtime wraps transport and never exposes raw mutation methods to model-bearing services.
- Framework capability catalog classifies methods as read, bounded write, developer/assisted, or prohibited.
- Reflective `engine.*`, generic RPC, developer actions, and unrestricted tools remain legacy/operator capabilities and are unavailable to framework selectors/planners.
- Bridge responses are untrusted until schema/capability validation.
- Loopback binding remains default and required for standard profiles.

## 4. Desired upstream-compatible enhancements

Only propose after proving need:

1. machine-readable method metadata: parameter/result schema, read/write classification, assisted flag, game-state prerequisites;
2. event gap/retention metadata and stable bridge build/version in health;
3. optional client correlation ID echoed in RPC result/ledger events;
4. explicit save/game identity suitable for recovery;
5. efficient batch reads or snapshot token to provide consistency across related observations;
6. generic safe-pause endpoint behavior if current game pause semantics are insufficient for watchdog use.

Agent-specific TTC, matrices, objectives, or policy do not belong in RimBridge.

## 5. Compatibility adapter

Contracts/runtime must support the reviewed baseline without requiring enhancements. Capability discovery normalizes informal method docs into a pinned local catalog. New metadata is additive. If a method is absent, domains declare a capability gap and cannot silently fall back to reflection in ranked mode.

## 6. Version pinning

The superproject pins an exact commit and records it in release/episode manifests. RimBridge updates require:

- build and test pass;
- method inventory diff;
- contract fixture replay;
- action classification review;
- shadow observation comparison;
- scored-series boundary activation.

## 7. Tests

- Existing RimBridge tests remain upstream-owned.
- Superproject contract tests replay representative envelopes and method inventory.
- Mutation gateway tests verify prohibited classes never escape dispatcher.
- Timeout/main-thread saturation/restart tests ensure runtime uncertainty handling.
- Event sequence gap and save identity fixtures cover recovery.

## 8. Acceptance

RimBridge remains usable independently of RimBrainAgent, contains no model or colony-strategy logic, and can be upgraded/pinned through explicit compatibility evidence. Framework runs use only declared capabilities and report a typed gap when one is unavailable.
