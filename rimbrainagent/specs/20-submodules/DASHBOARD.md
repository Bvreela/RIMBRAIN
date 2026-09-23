# Dashboard submodule build specification

**Status:** READY  
**Future path:** `components/dashboard`  
**Future remote:** `rimbrainagent-dashboard`  
**Base:** extract behavior from upstream `agent/rimagent/dashboard/app.py`

## 1. Purpose

Dashboard provides human observability and audited control without importing runtime internals or reading mutable files directly. It renders the runtime read model and canonical event projection.

## 2. Scope

- Live connection status and episode/revision identity.
- Objective, plan horizons, goal/task graph, workflow progress, blockers, locks.
- Pawn vitals/TTC, site runways, posture, hazards, spiral alarms.
- Attention queue and exact precedence/tie-break explanation.
- Matrix row, features/freshness, candidates/exclusions, route, qualification, fallback.
- Provider health, budgets, latency, cost, stale/rejected calls, calibration/drift.
- Dispatcher queue, actions, ownership, idempotency, verification/outcomes.
- RimBrain pack browser, semantic diff, proposals, fixtures, promotion/rollback lineage.
- Export/evaluation report links.
- Operator pause/resume/takeover/approval and controlled overrides.

## 3. Non-goals

- Direct RimBridge access.
- Editing mounted active pack files.
- Invoking provider adapters.
- Computing authoritative metrics.
- Silent control actions.
- Remote multi-user deployment in first release.

## 4. Boundary

Dashboard consumes:

- versioned HTTP read API for snapshots/projections;
- SSE/WebSocket canonical event projection;
- audited command API with command ID, expected state revision, actor, reason, and confirmation class.

It never imports runtime Python modules. The initial extraction may serve static assets from runtime for convenience, but build/release and contract tests remain independent.

## 5. Planned layout

```text
src/
  api-client/
  contracts/
  views/
    overview/
    survival/
    plan/
    attention/
    decisions/
    actions/
    rimbrain/
    evidence/
    evaluation/
    system/
  controls/
  state/
  redaction/
tests/
  contract/
  components/
  e2e/
```

Framework choice is selected during component bootstrap after checking existing project conventions and long-term maintainability.

## 6. Control classes

- Immediate safe controls: operator pause, safe pause request.
- Confirmed controls: resume, approve one supervised intent, clear operator hold.
- High-impact controls: activate pack at boundary, rollback, takeover, end episode.
- Development-only: inject fixture/event, enable assisted actions.

Every command shows resulting mode/ownership, persists through restart as appropriate, and emits requested/accepted/rejected/completed events. Resume never implicitly clears unrelated holds.

## 7. Upstream migration

Upstream FastAPI dashboard directly imports brain paths, skills, git, scorecard, watchdog, bridge, and control objects. Replace these with public APIs. Preserve useful event streaming and controls during transition through a compatibility backend, then remove direct imports after view parity.

The current single embedded HTML page should be treated as a prototype. Extract behavior and user workflows, not necessarily its implementation structure.

## 8. Security/privacy

- Bind loopback by default.
- Escape all game/model/operator text.
- Never render secrets or raw provider headers.
- Hidden reasoning is not a standard view.
- File browsing is limited to contract-provided sanitized artifacts.
- Remote exposure requires a later authenticated deployment spec.
- Destructive/high-impact controls require explicit confirmation and runtime authorization.

## 9. Tests

- API/SSE consumer contract tests.
- Reconnect/event-gap/hydration tests.
- Stale command revision rejection.
- Independent pause-state rendering.
- Candidate/exclusion/route trace rendering.
- XSS fixtures from pawn names, letters, mods, and model text.
- Accessibility and keyboard control checks.
- E2E against stub runtime read/control server.
- No direct imports/network calls to RimBridge.

## 10. Delivery increments

- **D0:** API client, live event shell, upstream status/control parity.
- **D1:** plan/task/survival/attention views.
- **D2:** matrix/provider/action/verification inspectors.
- **D3:** RimBrain proposal/diff/evidence views.
- **D4:** evaluation/export/system health views.

## 11. Acceptance

A reviewer can answer every human-reviewability question from the UI, all controls are audited and revision-safe, malicious text cannot inject UI behavior, reconnect preserves sequence integrity, and the dashboard runs without importing runtime implementation packages.
