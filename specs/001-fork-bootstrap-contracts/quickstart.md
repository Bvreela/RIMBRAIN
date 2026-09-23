# Quickstart Validation: Fork Bootstrap and Contract Foundation

Runnable end-to-end proof of the feature. All steps offline; no game, model, or secrets needed.
Prerequisites: Git, Python 3.12+ + `uv`, .NET SDK (Phase 0 entry gates).

## 1. Fork checkout (US-1, SC-001)

```powershell
git clone <superproject-url> rimbrainagent
cd rimbrainagent
git submodule update --init --recursive
```

Expected: `upstream/rimagent` at `85cb050`, nested `upstream/rimagent/mod` at `3c1e4c7`, clean
porcelain status.

## 2. Component validation shells (US-1, FR-003)

```powershell
# each component's no-op validation — passes with no game/model/network
components/contracts/validate.*   components/runtime/validate.*   # etc. per component README
```

Expected: every component reports `ok`.

## 3. Upstream parity (US-1, FR-004, SC-002)

```powershell
cd upstream/rimagent/agent; uv run pytest -q          # Python suite, unmodified
cd ../mod/Tests; dotnet test                          # RimBridge tests
cd ../../mod-steward/Tests; dotnet test               # Steward tests
```

Expected: identical pass set to upstream — the fork inherits behavior, nothing reimplemented.

## 4. Baseline bundle (US-2, FR-009)

```powershell
tools/baseline-capture     # generates baselines/upstream-85cb050/
tools/baseline-validate    # pin compare + porcelain scan + optional tree hash
```

Expected: `MANIFEST.yaml` sealed, `rpc-inventory.json` lists 115 methods, `gaps.yaml` records the
deferred live captures. Tamper test (SC-006): edit any file under `upstream/rimagent/`, re-run
`baseline-validate` → integrity failure naming the path. Revert after.

## 5. Contract corpus (US-3, FR-005/006, SC-003)

```powershell
tests/contract/run-corpus   # validates examples/valid + examples/invalid
```

Expected: 100% valid accepted, 100% invalid rejected with structured `{ok:false,error:{code,...}}`;
a `schema_version` bump on a valid object → explicit rejection, not silent pass.

## 6. Event mapping round-trip (US-4, FR-008, SC-004)

```powershell
tests/contract/run-event-map   # synthesized upstream-kind corpus → canonical → back
```

Expected: all 18 upstream bus kinds map to registered `event_type`s; original `{seq,kind,data}` payload
reproduced losslessly; unknown kind → `legacy.unmapped` (stored, not executable).

## 7. Fixture replay (US-5, FR-010/011, SC-005)

```powershell
tests/fixtures/replay fix.seed-001
tests/fixtures/replay fix.seed-001   # x5 → identical reports
tests/fixtures/replay fix.corrupt-001 # truncated fixture → named structural defect, no partial replay
```

Expected: deterministic comparison reports; corrupt fixture fails closed.

## Done when

All seven sections pass → feature acceptance criteria (SC-001..007) demonstrated.
