<!--
Sync Impact Report (temporary — remove before commit)
- Version change: none → 1.0.0 (initial ratification); 1.0.0 → 1.1.0 (added Principle IX);
  1.1.0 → 1.2.0 (added Principle X + pack-class/single-executable/standing-goal constraints)
- Principles: 8 established, consolidated from specs/00-foundation/ENGINEERING-PRINCIPLES.md P1–P15
  and the architectural invariants in AGENTS.md; IX and X added from feature 012/015 work
- Added sections: Safety and Operational Constraints; Development Workflow and Quality Gates; Governance
- Removed sections: none (template placeholders only)
- Deferred items: none
-->

# RimBrainAgent Constitution

## Core Principles

### I. Deterministic Before Probabilistic

Code decides whenever legality, arithmetic, freshness, ordering, idempotency, or a hard safety
invariant determines the answer. A model is justified only for unresolved tradeoffs or novel
strategic synthesis. Unknown or stale safety-critical state causes observation or safe pause —
never a guess; noncritical gaps may use only an explicitly declared fallback.

### II. One Writer, Bounded Model Authority (NON-NEGOTIABLE)

Every game mutation passes through a single serialized dispatcher. Models emit typed choices or
proposals — the selector picks one offered option ID, the planner proposes plans — and never hold
bridge mutation handles or issue unrestricted RPCs. Emergency and reflex paths have no provider
dependency and never wait on a model.

### III. Spec-First Development (NON-NEGOTIABLE)

Every change begins as a versioned specification with stable requirement IDs. Cross-component
behavior begins with a versioned contract plus consumer/provider tests. Architectural changes
require an ADR before code. A feature is not complete until its traceability row links passing
evidence. Undeclared dependency directions are forbidden.

### IV. Explicit Compatibility

Every interface and artifact declares a schema/contract version; consumers reject unknown newer
schemas. Releases pin exact submodule commits, pack hashes, and model revisions. Migrations run
between scored series, never during them. New repositories are split only when a boundary has an
independent release cadence, a stable public contract, external consumers, and independent tests.

### V. Evidence Is Immutable; Policy Is Revisable Data

Observations, decisions, responses, actions, and outcomes are append-only canonical flat-file
records; indexes are disposable projections. Reusable matrices, workflows, prompts, and lessons
belong to versioned, hashed RimBrain packs — per-episode plans, locks, and cursors belong to
runtime state. Policy activates atomically at episode boundaries and is immutable during scored
runs; no component promotes its own proposals.

### VI. Granular Qualification, Staged Promotion

No model is globally trusted. Selector authority is qualified per matrix row, model revision,
prompt/renderer revision, and context family; drift or calibration failure demotes only the
affected tuple. Provider behavior, policy patches, and action templates pass offline fixtures and
contract tests, then shadow mode, then bounded live trials before live authority.

### VII. Build for Diagnosis

Every route, exclusion, fallback, lock, validation rejection, write, and verifier result emits a
causal event. A reviewer must be able to reconstruct any behavior from exported evidence without
source-level debugging or access to private chain-of-thought.

### VIII. Migration Escape Hatch

Upstream legacy play remains an opt-in recovery and baseline-comparison mode while the framework
matures. It must never share write authority with framework mode and can never qualify as a
scored framework run.

### IX. Policy Is Data; Code Is Capability (NON-NEGOTIABLE)

All gameplay strategy, tactics, priorities, and decision logic — start sequences, combat rules,
work scheduling, resource policy, and long-horizon planning — live exclusively in human-editable,
schema-validated RimBrain packs. Runtime code provides only capability primitives: generic
predicates, selectors, phase/rule/step interpreters, and action templates. Hardcoding how the
colony starts, fights, or prioritizes is an antipattern; a pack must be able to redefine, reorder,
extend, or disable any executed behavior without code changes.

### X. Brain Lifecycle Is Explicit and Residue-Free (NON-NEGOTIABLE)

The RimBrain — loaded pack revision, decision matrices, universal policies, planning layers,
and task-ledger namespaces — is a single loadable/unloadable entity. Load, unload, swap,
refresh, and reset fully reinitialize every layer; tombstoned namespaces are durable and
replay-safe across restarts. No gameplay rules, planning, or writes occur while no pack is
loaded, and no pack change may leave residual state in the engine or the ledger. Lifecycle
correctness is verified by continuous-loop tests (load → drive → unload → reload → swap);
failures found there are defects to fix, never tolerances.

## Safety and Operational Constraints

- RimBridge stays generic; agent-specific deterministic policy lives in Steward or the runtime.
- All Verse work executes on the Unity main thread; RPC failures return `{ok:false,error}` and
  are never thrown into Unity.
- RimBridge binds loopback only; no remote game control surface.
- Secrets, endpoints, and credentials never enter specs, packs, logs, or exports; community
  RimBrain packs are untrusted data and carry no auto-executed code.
- Runtime, policy, evidence, and export data have separate ownership roots.
- Packs declare `class: fair | dev`; fair runs refuse dev-method packs at load and dev actions
  at dispatch. Vanilla fair packs carry zero debug/developer instructions; troubleshooting
  tooling lives only in dev-class packs.
- Standing governance goals are pack-defined invariants: they re-arm whenever their verified
  effect lapses (e.g. a destroyed stockpile) and back off after failed convergence so one
  blocked goal cannot starve the poll.
- The app ships as a single executable; read-only data (schemas, RPC inventory, event map,
  bundled packs/profiles) lives inside the image while writable data (state, editable packs,
  profiles) resolves beside it — never inside. Packaging must not weaken fair-mode refusal,
  pack-drift rejection, or the single-writer guarantee.
- Baseline toolchain: Python 3.12+ with `uv`, .NET SDK for RimWorld 1.6 mod targets, PowerShell
  helper scripts on Windows.

## Development Workflow and Quality Gates

- Feature work follows the Spec Kit pipeline: constitution → specify → clarify → plan → tasks →
  analyze → implement → converge. Project-level normative volumes live in `specs/`; per-feature
  workspaces live in `specs/<NNN>-<slug>/`.
- Every work package declares requirements, interfaces, tests, migration, rollback, and measurable
  exit criteria before implementation starts.
- Verification ladder, in order: unit/contract tests → offline fixtures and replay → shadow mode →
  bounded live trials → monitored cohort. Baseline suites: `uv run pytest -q` (agent),
  `dotnet test` (RimBridge and Steward test projects).
- `upstream/rimagent` is read-only migration input; fork implementation never edits inside it, and
  `.gitmodules` never uses local filesystem URLs.
- Release and episode manifests record submodule commits, schema versions, pack hashes, model
  revisions, and build identity.

## Governance

- This constitution supersedes ad-hoc practice. Where documents conflict, precedence follows
  `AGENTS.md` "Sources of truth": unified requirements → contracts → submodule specs → ADRs →
  traceability.
- Amendments require a written proposal, an ADR for architectural impact, and an explicit version
  bump (MAJOR: principle removal/redefinition; MINOR: new or materially expanded principle;
  PATCH: clarification only).
- Every specification review, PR, and release-acceptance check verifies compliance with these
  principles; complexity beyond them must be justified in the spec.
- Use `AGENTS.md` for runtime development guidance and `specs/INDEX.md` for the authoritative
  document inventory.

**Version**: 1.2.0 | **Ratified**: 2026-09-22 | **Last Amended**: 2026-09-23
