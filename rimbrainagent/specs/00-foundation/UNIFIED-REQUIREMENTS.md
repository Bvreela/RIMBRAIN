# Unified requirements

**Status:** READY  
**Source:** Consolidated from the approved unified RIMagent architecture and build specification.  
**Requirement form:** `UR-<area>-<number>`; `MUST`, `SHOULD`, and `MAY` are normative.

## Control and safety

- **UR-CTL-001:** The system MUST have exactly one framework game-write dispatcher.
- **UR-CTL-002:** Components with provider clients MUST NOT possess or invoke game-write capabilities.
- **UR-CTL-003:** Models MUST return typed offered choices or schema-valid proposals; free-form text MUST NOT execute.
- **UR-CTL-004:** Every write MUST carry intent/idempotency IDs, pinned revisions, fresh preconditions, ownership, bounds, and verification schedule.
- **UR-CTL-005:** Emergency response MUST be deterministic and MUST NOT wait for a provider.
- **UR-CTL-006:** Unknown, stale, contradictory, malformed, unoffered, mismatched, or late decision inputs MUST fail closed.
- **UR-CTL-007:** Operator pause, game pause, and dispatcher ownership MUST be separately persisted.
- **UR-CTL-008:** Framework and legacy controllers MUST never hold concurrent write authority.
- **UR-CTL-009:** Runs MUST be able to declare fair mode (no debug cheating): the dispatcher MUST refuse `dev.*` methods and save/load calls before any bridge invocation; refusals MUST be logged and visible in decision records. Fair mode MUST also disable the in-game dev/debug UI (`Prefs.DevMode`, god mode) for the run duration and restore the player's prior setting on exit.

## Runtime and recovery

- **UR-RUN-001:** Runtime MUST execute the spine `reconcile → attend → route → dispatch → verify → evidence`.
- **UR-RUN-002:** Tasks MUST use the declared lifecycle and only a verifier may mark success.
- **UR-RUN-003:** Pending actions MUST reconcile observed effects before retry after timeout or restart.
- **UR-RUN-004:** Runtime state MUST survive process restart through durable canonical files.
- **UR-RUN-005:** A stalled reconciliation heartbeat while unattended MUST trigger safe pause.
- **UR-RUN-006:** Repeated identical failures MUST trip a context-scoped circuit breaker.
- **UR-RUN-007:** Thresholds MUST define enter/exit hysteresis and relevant dwell/cooldown.
- **UR-RUN-008:** Provider calls MUST be cancellable, deadline-bound, revision-correlated, and stale-rejected.
- **UR-RUN-009:** Start Mode completion (`start.completed`) MUST be a handoff, not an exit: under a held run the pack's `govern` standing goals keep driving the colony (sustainment objectives that re-arm on regression, plus stability-gated ambitions such as tech progression and mission offers); bounded callers MAY still stop at completion.

## Survival and attention

- **UR-SUR-001:** Every living pawn MUST have freshness-bounded vitals with time-to-critical where supported.
- **UR-SUR-002:** Pawn-level safety conditions MUST NOT be gated by colony averages.
- **UR-SUR-003:** AMBER-or-higher life-critical attention MUST order by TTC and deterministic triage value.
- **UR-SUR-004:** Site-specific runway MUST cover survival and maintenance resources, including caravans.
- **UR-SUR-005:** Persisted posture MUST implement GREEN, AMBER, RED, and BLACK semantics.
- **UR-SUR-006:** Hard safety invariants MUST be validated immediately before dispatch.
- **UR-SUR-007:** Deaths and near-misses MUST produce timeline-based post-mortems and fixture proposals.
- **UR-SUR-008:** Evaluation MUST use lexicographic integrity, life, maintenance, progress, then efficiency priorities.
- **UR-SUR-009:** Episodes MUST declare progress floors and report pause/stall behavior.

## Model routing

- **UR-MOD-001:** Provider roles MUST be vendor-neutral and independently configured.
- **UR-MOD-002:** Tier 0 MUST own emergencies, legality, arithmetic, observation, verification, already-satisfied states, and single-option choices.
- **UR-MOD-003:** Tier 1 MUST choose exactly one offered option or abstain.
- **UR-MOD-004:** Selector authority MUST be qualified per matrix row/model/renderer revision against rules and calibration gates.
- **UR-MOD-005:** Rules MUST remain an immediate fallback for every selector-routed row.
- **UR-MOD-006:** Tier 2 MUST run only on declared planning, novelty, conflict, failure, milestone, or review triggers.
- **UR-MOD-007:** Model packets MUST be deterministic renderings of validated, freshness-tagged features with enforced budgets.
- **UR-MOD-008:** Untrusted game/mod text MUST be delimited and MUST NOT originate executable IDs or parameters.
- **UR-MOD-009:** Planner proposals MUST include assumptions, falsifiable predicates, verification, predictions, and pre-mortem.
- **UR-MOD-010:** High-impact/life-critical plans MUST support a bounded plan-critique sequence.
- **UR-MOD-011:** A nonsecret endpoint registry MUST declare named LLM endpoints (id, label, base_url, API shape, advertised models, capabilities such as tool-calls/thinking/embeddings) separately from role bindings; local and remote endpoints use the same registry.
- **UR-MOD-012:** Secrets (API keys) MUST live outside the registry — referenced by name from environment variables or a gitignored local file; keys MUST NOT be committed, logged, or embedded in canonical records/packs.
- **UR-MOD-013:** Role bindings MUST map semantic roles (e.g. `rimbrain.plan`, `rimbrain.select` for action-matrix rows, `rimbrain.review`, `rimbrain.embed`) to endpoint+model independently; a binding change is runtime state, never a mutation of the active RimBrain pack.
- **UR-MOD-014:** A user-facing selection UI MUST list configured endpoints, probe health/capabilities, and persist role bindings without hand-editing YAML; hand-editing the registry MUST remain equally valid.
- **UR-MOD-015:** Local endpoint discovery SHOULD probe well-known local servers (LM Studio :1234, Ollama :11434, vLLM :8000, llama.cpp :8080) via `/v1/models` enumeration.
- **UR-MOD-016:** The resolved endpoint+model+revision for each role MUST be recorded in episode/run manifests (provenance); bindings in effect at episode start are pinned for scored episodes.
- **UR-MOD-017:** A binding MUST fail closed: an endpoint that fails health or capability checks (e.g. no tool-calls for a tool-calling role) MUST NOT be bound — the role falls back to its declared degraded path (rules or a qualified smaller model).

## RimBrain policy

- **UR-BRN-001:** Reusable policy MUST live in human-readable, schema-validated RimBrain packs.
- **UR-BRN-002:** Runtime state, private evidence, and reusable policy MUST have separate roots.
- **UR-BRN-003:** Every executable policy object MUST have a stable ID and revision; references MUST bind revisions.
- **UR-BRN-004:** Active policy and prompts MUST be immutable during scored episodes.
- **UR-BRN-005:** Planners/reviewers MAY propose patches but MUST NOT activate them.
- **UR-BRN-006:** Pack activation MUST occur atomically at an allowed boundary with rollback lineage.
- **UR-BRN-007:** Community packs MUST be hashed, compatibility-declared, provenance-preserving, and optionally signed.
- **UR-BRN-008:** Pack-provided executable code MUST NOT auto-apply.
- **UR-BRN-009:** The fixture suite MUST be append-only by default and mandatory in release validation.
- **UR-BRN-010:** Always-on prediction-error aggregation MUST create review obligations without requiring a model call.
- **UR-BRN-011:** All gameplay strategy, tactics, priorities, and decision logic — start sequences, combat behavior, work scheduling, resource flow, and long-horizon planning — MUST be expressed as editable RimBrain pack data (configuration, decision matrices, or declarative policy files); it MUST NOT be embedded in source code.
- **UR-BRN-012:** Runtime code MUST provide capability primitives only — generic predicates, selectors, phase/rule/step interpreters, and action templates — sufficient to execute any pack-defined strategy. Hardcoded gameplay direction, phase orderings, thresholds, or heuristics are forbidden.
- **UR-BRN-013:** A pack MUST be able to redefine, reorder, extend, or disable any behavior the runtime executes — including start phases, combat steps, and universal rules — without code changes.
- **UR-BRN-014:** The pack schema MUST version the policy primitive vocabulary so packs declare compatibility against the capabilities the runtime exposes.
- **UR-BRN-015:** The engine MUST maintain a versioned capability catalog covering every action, mechanic, and interaction exposed by the bridge and documented by authoritative sources (e.g. the RimWorld Wiki); each catalog entry MUST map to an implemented primitive or be explicitly marked a known gap.
- **UR-BRN-016:** Capability coverage MUST be auditable: tooling MUST diff the bridge RPC surface and documented mechanic domains against the catalog and report unmapped surface; coverage gaps MUST never be silently absent.
- **UR-BRN-017:** Capability primitives MUST remain strategy-agnostic; the catalog and primitives MUST NOT carry when/why/threshold/priority policy — how capabilities are used is pack data only.
- **UR-BRN-018:** Packs MUST declare `class: fair|dev`. A fair-class pack MUST contain zero `dev.*` methods end to end; a dev-class pack MUST be refused at load under a fair run. Multiple packs MUST coexist in the pack library, loadable by id with independent hashes/revisions.
- **UR-BRN-019:** The RimBrain (pack + interpreter state) MUST be a single loadable/unloadable entity: load by pack id, swap to a different pack, refresh the active pack, and unload (halt all pack-driven writes) through a UI-reachable control channel — without restarting the run and without breaking gameplay logic.
- **UR-BRN-020:** A brain reset MUST fully reinitialize the brain's decision state — task-ledger namespaces (start/govern/combat tasks tombstoned with durable evidence), pack var bindings, rule/step cooldowns, and planning-layer state — while observed colony state remains the only world truth. A reset MUST NOT leave residual tasks, cooldowns, or stale hashes that alter post-reset behavior, and it MUST replay correctly after process restart.
- **UR-BRN-021:** The pawn-level decision matrix MUST offer a broad, varied option set — per-pawn job assignment, work-type priorities, drafting, equipment, rescue, medical, and scheduling — with per-pawn selection resolved on skill, traits, and capability, never a fixed pawn or fixed job.
- **UR-BRN-022:** All build-space selection, layout direction (site geometry, room placement, orientation, expansion), and construction logic MUST be expressed in RimBrain pack data and resolved through capability primitives; the engine MUST NOT hardcode placement, orientation, or layout strategy.
- **UR-BRN-023:** Brain load/unload/reset correctness MUST be verified by a continuous-loop test (load → drive → unload → reload → drive, repeated); every failure the loop discovers MUST be fixed, not documented around.
- **UR-BRN-024:** Power-generator siting MUST validate a pack-declared clearance corridor (e.g. a wind turbine's airflow path) — buildings, walls, and natural objects that would block it veto the site; the corridor geometry (axis, half-width, depth, gap), which thing kinds obstruct, which designator clears vegetation, and the regrowth-suppression follow-up (none | flooring | growing zone) are all pack data, never engine constants. Step `when`/`needs` predicates MUST be able to gate per `for_each` candidate (`@var:it`).

## Transparency and observability

- **UR-VIEW-001:** The system MUST render a real-time Planning & Goals view showing the agent's active objectives, ordered priorities, per-goal state, exit-condition evaluation, and blockers.
- **UR-VIEW-002:** The system MUST render a real-time Quick-Action Matrix showing every dispatched capability primitive per poll, with source (pack rule/phase), resolved parameters, and outcome.
- **UR-VIEW-003:** Both views MUST be synchronized per poll, derived from canonical records, and traceable to the pack revision that produced the behavior.
- **UR-VIEW-004:** Views MUST expose decision surfaces (which rule fired, which predicate gated it, what resolved) but MUST NOT expose private model chain-of-thought or secrets.

## Persistence and evidence

- **UR-DAT-001:** Canonical runtime/evidence records MUST be flat-file, schema-versioned, and recoverable.
- **UR-DAT-002:** Append-only records MUST be flushed durably before acknowledgement; torn final records MUST recover explicitly.
- **UR-DAT-003:** Mutable state MUST use atomic replacement with tested Windows behavior.
- **UR-DAT-004:** Every decision MUST record revisions, fresh features, candidates/exclusions, route, selected/executed actions, expected/actual outcomes, and intervening incidents.
- **UR-DAT-005:** The system MUST NOT infer outcomes for unchosen options.
- **UR-DAT-006:** Secrets and unsafe paths MUST NOT enter policy, evidence, proposals, or exports.
- **UR-DAT-007:** Derived databases/indexes MUST be disposable and rebuildable.

## Export and external reuse

- **UR-EXP-001:** Every episode MUST be exportable as a schema-versioned causal event stream.
- **UR-EXP-002:** JSONL MUST be canonical; analytics formats MAY be derived and hash-linked.
- **UR-EXP-003:** Export MUST support audit, analysis, training, and community profiles.
- **UR-EXP-004:** Training exports MUST represent state, candidates, choice, action, delayed outcome, horizon, censoring, and candidate masks.
- **UR-EXP-005:** Shared exports MUST use allowlist redaction, pseudonymization, checksums, manifest, and data card.
- **UR-EXP-006:** Exports MUST mark interventions, reloads, missingness, stale data, rejected decisions, and assistance.
- **UR-EXP-007:** Dataset splits MUST group by start-save family to prevent correlated leakage.
- **UR-EXP-008:** Export MUST NOT alter canonical source logs or expose private reasoning by default.
- **UR-EXP-009:** Independent consumers MUST be able to verify an export and reconstruct decision-to-outcome lineage.

## Modularity and delivery

- **UR-ARC-001:** Cross-component dependencies MUST follow the declared acyclic direction.
- **UR-ARC-002:** Release builds MUST pin exact component/submodule commits and compatibility versions.
- **UR-ARC-003:** RimBridge MUST remain generic; agent policy belongs in Steward, runtime, or RimBrain.
- **UR-ARC-004:** Components MUST expose versioned contracts and independent contract tests.
- **UR-ARC-005:** The fork MUST retain attribution and third-party license notices.
- **UR-ARC-006:** Implementation MUST proceed through measurable work packages with requirement/test traceability.
- **UR-ARC-007:** Dashboard and lab MUST consume public contracts rather than runtime internals.
- **UR-ARC-008:** Scored runs MUST reject dirty or unrecorded component states.
- **UR-ARC-009:** The full app — runtime loop plus dashboard overlay — MUST ship and launch as a single executable. One command (`rimbrain run`) starts brain and UI together; a `rimbrain overlay` subcommand is the frozen child-entry so the same binary serves both roles. Packs, contract schemas, the RPC inventory, event map, and endpoint profiles MUST be bundled read-only, while state, editable packs, and profiles resolve beside the executable — never inside it. Pack load/unload/swap/reset through the packaged UI MUST behave identically to source runs, and packaging MUST NOT weaken fair-mode refusal, pack-drift rejection, or the single-writer guarantee.

## Checkpoint-retry loops (debug/eval)

- **UR-RL-001:** The system MUST support checkpoint-reload retry loops — save, advance a configured game-time window, evaluate a gate, reload and retry on failure — via bridge save/load/status/speed RPCs.
- **UR-RL-002:** Loop config MUST declare game-time window, retry cap, checkpoint family, gate, mutation space, and budgets; all recorded in the run manifest.
- **UR-RL-003:** The gate MUST support early exit — a passing iteration ends remaining retries for that increment.
- **UR-RL-004:** Each retry MUST apply one recorded mutation from a declared space; identical retries are forbidden; invalid mutations are rejected with the prior revision kept.
- **UR-RL-005:** Every iteration MUST emit canonical events (checkpoint/window/gate/mutation/verdict) and export as a replayable fixture per the fixture-package contract.
- **UR-RL-006:** Retry loops MUST refuse to run inside scored episodes and never mutate an immutable pack in place — mutations produce new candidate revisions.
