# ADR-013: Bridge layer — zorrobyte RimBridge primary, gateway-shaped adapter boundary

**Status:** PROPOSED
**Date:** 2026-09-22
**Owners:** rimbrainagent maintainers
**Related requirements/specs:** ADR-010 (keep RimBridge generic), specs/20-submodules/RIMBRIDGE.md, specs/20-submodules/RUNTIME.md, specs/001-fork-bootstrap-contracts (T004), specs/50-verification/E2E-TEST-ENVIRONMENT.md (TE-010..015)

## Context

The unified spec assumed **zorrobyte RimBridge** (loopback HTTP JSON-RPC on `127.0.0.1:8765`, 115 methods, `{ok,result|error}` envelopes, `/events` feed, optional **Steward** add-on supplying the deterministic Tier-0 surface).

On the dev machine a *different* bridge is installed and live: **pardeike RimBridgeServer** (`brrainz.rimbridgeserver`, GABP protocol on `127.0.0.1:5174`, token auth, 125-tool surface, semantic UI state, attention policy, Lua scripting, DPA profiling, GABS ecosystem). Verified same-day: both bridges serve simultaneously in one game instance with no conflict.

## Decision drivers

- One-writer safety: the runtime dispatcher must own a serializable mutation path.
- Tier-0 determinism: Steward (scorer/stock/standing orders) exists only on the zorrobyte mod.
- Migration lineage: our fork pins zorrobyte/rimagent as upstream; the agent loop already speaks its RPC surface.
- Dev-tooling quality: GABP surface is richer for inspection/debugging (semantic UI, attention, DPA).
- Proven coexistence: ports/protocols don't collide; dual operation is free.

## Options considered

### Option A — zorrobyte RimBridge only

Spec baseline. Single protocol, simplest dispatcher. Steward required regardless for Tier-0.

### Option B — GABP (RimBridgeServer) primary

Better dev tooling, active maintenance by Harmony's author, designed for AI harnesses. But no Steward equivalent, different protocol (LSP-framed GABP vs HTTP), and abandons upstream lineage the migration specs are built on.

### Option C — Dual-adapter gateway

Runtime speaks to an abstract bridge interface; zorrobyte HTTP and GABP adapters behind it. Maximum flexibility, extra abstraction cost, two surfaces to qualify.

## Decision

**Option A, with a gateway-shaped adapter boundary.** RimBridge (HTTP) is the sole game-write transport; the runtime's bridge client is written behind an interface (`capabilities`/`call`/`events`) so a GABP adapter can be added later without touching policy. RimBridgeServer may remain enabled in dev sessions as a *read/diagnostic* sidecar — it never receives mutation authority. Steward stays mandatory in framework runs.

## Consequences

### Positive

- Baseline inventory (115 methods) is directly diffable; T019 extractor targets `[Rpc]` attributes as planned.
- Steward tier-0 + one serialized HTTP dispatcher = the simplest path satisfying constitution (one writer, deterministic-first).
- No game config change needed — both mods already coexist; devs keep GABP tooling for free.
- GABP adapter is a future extension point, not a rewrite.

### Negative

- We do not adopt GABP's richer semantic-state/attention surface now — diagnostic-only.
- Maintaining the adapter interface has some cost even with one implementation.

## Compatibility and migration

- `tools/bridgecheck/bridge_check.py` already probes both protocols — remains the TE-015 gate.
- `upstream/rimagent` client code (`bridge.py`) is reference for the HTTP adapter; GABP session/token flow documented in feature-002 notes.
- If ADR-010 is ever revisited (drop zorrobyte), this ADR must be revisited with it.

## Verification

- bridge_check 9/9 live 2026-09-22 (both bridges, game at Entry state).
- env-check now detects mod enablement (`zorrobyte.rimbridge` in activeMods) and both ports.

## Revisit/kill criteria

- zorrobyte/rimbridge stalls or breaks on a RimWorld update while RimBridgeServer stays maintained → re-evaluate Option B.
- GABP gains a Steward-equivalent deterministic layer → reconsider primary.
- Adapter interface proves heavier than value → collapse to direct HTTP client (Option A pure).
