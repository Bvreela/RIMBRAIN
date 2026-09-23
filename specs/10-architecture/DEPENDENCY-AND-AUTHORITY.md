# Dependency and authority rules

**Status:** READY

## 1. Compile/import dependency graph

```text
contracts
  ▲      ▲       ▲        ▲         ▲
  │      │       │        │         │
rimbrain runtime steward  lab    dashboard
          ▲       ▲
          │       │
       rimbridge ◄┘
```

More precisely:

- `contracts` depends on standard schema tooling only.
- `rimbrain` depends on contracts for validation semantics, not runtime.
- `runtime` depends on contracts and network protocols exposed by RimBridge/Steward.
- `steward` depends on RimBridge assembly and generated/hand-maintained contract bindings.
- `lab` depends on contracts and reads RimBrain/export artifacts.
- `dashboard` depends on contracts and runtime’s public HTTP/SSE APIs.
- RimBridge depends on none of the agent-specific components.

The superproject is not imported by components.

## 2. Game authority graph

| Capability | Bridge | Steward | Runtime dispatcher | Other runtime services | Models | Dashboard | Lab |
|---|---:|---:|---:|---:|---:|---:|---:|
| Read game | Yes | Yes | Yes | Via read gateway | Packet only | Read API only | No live access |
| High-frequency deterministic writes | Executes | Own scope | Coordinates policy | No | No | No | No |
| Framework bounded writes | Executes | If template targets Steward | **Owns** | No | No | No | No |
| Select offered choice | No | Fixed rules | No | Router applies | Tier 1 only | Operator override | Replay only |
| Propose plan/policy | No | No | No | Planner/reviewer service | Tier 2 only | Human | Offline reviewer |
| Activate policy | No | No | Boundary coordinator | No | No | Authorized command | Promotion tool with human gate |

## 3. Role-scoped runtime dependencies

Define separate dependency containers rather than one upstream-style `Context`:

- `ObservationDeps`: read gateway, clock, event sink.
- `PlanningDeps`: frozen planning view, provider adapter, event sink; no dispatcher/gateway mutation.
- `SelectionDeps`: decision packet, selector adapter, event sink; no arbitrary state read.
- `DispatchDeps`: mutation gateway, policy snapshot, lock store, verifier scheduler, event sink; no provider.
- `VerificationDeps`: read gateway, predicate registry, event sink; no mutation.
- `DashboardDeps`: read model and command queue only.

Import-boundary tests fail if provider packages import dispatcher/mutation modules or domains import concrete adapters.

## 4. Data authority

- RimBrain pack: reusable policy authority for one pinned episode.
- Runtime state store: current episode execution authority.
- Canonical event store: audit/evidence authority.
- Export bundle: immutable projection, never write-back authority.
- Lab indexes/statistics: derived and disposable.
- Dashboard cache: derived and disposable.
- Legacy `brain/`: authority only in legacy controller mode.

## 5. Policy authority

A loaded pack can describe only registered concepts. Runtime code owns schemas, hard invariants, dispatcher semantics, verifier semantics, evaluator definitions, and executable action implementations. Packs own bounded instances: matrices, parameters within schema bounds, task/workflow graphs, prompt text, rules, and reviewed lessons.

## 6. Mutation boundaries

- Models never write files directly in framework mode.
- Reviewer output enters `runtime/proposals/<id>` through a validating proposal writer.
- Human edits target a working pack checkout, not the mounted active snapshot.
- Activation creates/verifies a new immutable snapshot and swaps a manifest pointer at an allowed boundary.
- Lab may write proposals/results but cannot change the runtime pointer.

## 7. Legacy isolation

Legacy mode may use dynamic bridge tools, `rpc`, `run_python`, hot-loaded tools/watchers, parallel roles, and brain mutation exactly as upstream. Framework mode must construct none of those capabilities. A process may instantiate one controller mode at a time. Mode switching requires game pause, shutdown/restart or a fully reconciled controller handoff specified later; Phase 1 uses restart-only switching.

## 8. Network boundaries

- RimBridge listens on loopback only.
- Local selector endpoints default to loopback.
- Hosted providers are accessed only through provider adapters and secret references.
- Dashboard defaults to loopback; remote exposure requires a separate authenticated deployment profile.
- Pack registries and community upload are offline CLI operations initially, not runtime network dependencies.

## 9. Enforcement

- Static import rules in component tests.
- Constructor typing that makes forbidden capabilities unavailable.
- Contract tests with malicious/malformed inputs.
- Runtime audits asserting every action event has dispatcher identity.
- CI scans for direct bridge mutation calls outside gateway/legacy allowlists.
- Release checks for component cleanliness, exact revisions, and policy immutability.
