# RIMagent — Unified Agent Architecture and Build Specification

**Status:** Final design baseline  
**Purpose:** Unify the strongest compatible ideas from the four prior RIMagent specifications into one implementable architecture.  
**Target:** A local-first, provider-neutral RimWorld agent built on RimAgent, RimBridge, and Steward.  
**Primary objective:** Keep pawns alive and healthy while making honest, measurable progress toward an operator-selected colony objective.  
**Design maxim:** Deterministic code acts; small models choose; large models plan and improve; humans can inspect and edit the entire brain.

---

## 1. Decisions made by this specification

This document resolves the major conflicts in the earlier specifications.

1. **Three control tiers, one writer.** Tier 0 deterministic automation owns reflexes and routine execution. Tier 1 uses a small model such as Laya or Jev only for bounded tactical choices. Tier 2 uses a capable model for sparse strategic planning, critique, repair, and policy review. Every game write still passes through one local dispatcher.
2. **Rules are the permanent baseline.** Laya is the preferred local Tier-1 candidate and Jev is an optional hosted candidate, but neither receives authority merely by being configured. A selector qualifies separately for each matrix row by beating or matching the deterministic rule on fixtures and passing calibration gates. An unqualified row uses rules.
3. **The strategic role is provider-neutral.** GLM is a supported and attractive planner/reviewer deployment, not an architectural dependency. Any endpoint that passes the same contracts and capability tests may fill the role.
4. **`rimbrain` is the shareable policy layer.** It is human-readable, schema-validated, versioned, diffable, and independently distributable. Runtime state is not mixed with reusable policy. Active policy is frozen during scored play; evolution creates reviewed patches rather than silently rewriting the live brain.
5. **Survival drives attention.** Pawn-level time-to-critical, colony runway, a crisis ladder, hard safety invariants, and deterministic emergency paths take precedence over generic task scoring.
6. **Self-improvement is continuous in evidence collection but gated in activation.** Every decision produces a prediction and verification result. Error clusters create fixtures and proposals. No model may activate its own proposal.
7. **Structured export is a first-class product interface.** Every episode can produce a portable, sanitized, schema-versioned dataset of observations, events, decisions, model responses, actions, outcomes, and causal lineage for external analysis or training.
8. **Modularity is protocol-first.** Components have narrow contracts and can live in separate repositories or Git submodules. The initial build avoids excessive repository fragmentation; only independently versioned, reusable boundaries become submodules.

---

## 2. Goals, non-goals, and falsifiable bets

### 2.1 Goals

RIMagent shall:

- play from landing or an adopted save through stable midgame and an operator-selected endgame;
- coordinate survival, labor, food, shelter, temperature, health, mood, logistics, power, research, production, defense, trade, people, animals, caravans, quests, and recovery as one constrained plan;
- use no model for emergencies, legality, arithmetic, already-satisfied goals, verification, or routine pawn work;
- use a small local or low-cost selector for qualified tactical decisions without granting it arbitrary tool access;
- use a larger model only for long-horizon planning, novelty, cross-domain conflict, repeated failure, and offline review;
- survive process restart without duplicating uncertain writes or losing task lineage;
- keep plans, matrices, prompts, workflows, knowledge, and proposed improvements human-readable;
- let community members fork, test, share, sign, and review `rimbrain` packs;
- expose why attention was assigned, what options existed, what was selected, what executed, and what happened;
- export complete machine-readable histories without leaking credentials or private operator data.

### 2.2 Non-goals for the first production release

RIMagent shall not initially:

- ask a model to choose every pawn job, tick, target cell, or hauling destination;
- execute free-form model prose, generated Python, invented RPC names, or unoffered IDs;
- require multiple cooperating agent processes;
- use live reinforcement learning or unrestricted exploration;
- mutate active policy during ranked or scored episodes;
- treat model confidence as game-success probability without row-specific calibration;
- infer outcomes for options that were not selected;
- optimize wealth or survival as a single scalar at the expense of deaths, progress, or pause abuse;
- execute code delivered inside a community brain pack in the first release;
- build a general spatial optimizer before fixed, phased layout templates prove insufficient.

### 2.3 Falsifiable bets

- **B1 — deterministic-first control:** rules plus Steward should outperform the legacy free-form-per-wake loop on integrity and maintenance. If not, stop expanding the framework and diagnose the spine.
- **B2 — small-model tactical value:** a Tier-1 model must outperform or meaningfully complement rules on row-specific replay fixtures and matched trials. Rows that fail remain deterministic.
- **B3 — sparse planning value:** planner-triggered repairs must reduce repeated failures, missed milestones, or plan churn. Otherwise the planner becomes advisory and plans remain human-authored.
- **B4 — policy iteration value:** frozen improved packs must outperform their parent on declared metrics without guardrail regression. Otherwise keep packs read-only and retain the evidence/replay tooling.

Kill thresholds and evaluation budgets must be declared before each experiment, not after results are known.

---

## 3. Non-negotiable invariants

1. **Single writer:** every framework game mutation flows through one dispatcher queue. Code holding a provider client has no game-write handle.
2. **Typed intent:** models return offered option IDs or schema-valid proposals. They do not emit executable commands.
3. **Emergency independence:** life-threatening response cannot call or wait for a model.
4. **Freshness:** the dispatcher rejects an action whose required observation or pawn vital is stale, unknown, or contradictory.
5. **Verifier-only success:** a task cannot mark itself successful. A fresh verifier returns `pass`, `fail`, or `unknown`.
6. **Desired-state idempotency:** dispatch expresses the intended state and checks for it before retrying.
7. **Durable truth:** human-readable files and append-only records are authoritative; in-memory and database indexes are rebuildable.
8. **Frozen scored policy:** a scored episode pins code, brain pack, prompt, model, adapter, and schema revisions.
9. **No self-promotion:** planners and reviewers may propose changes but cannot activate them.
10. **Safe uncertainty:** unknown critical state means pause and observe, not guess and act.
11. **Human override:** operator pause blocks writes, persists across restart, and is separate from game pause and dispatcher ownership.
12. **No hidden reasoning dependency:** decisions may store concise rationales and structured claims, but execution and exported data never depend on private chain-of-thought.

---

## 4. Runtime architecture

```text
RimWorld + RimBridge + Steward
        │ events, state, RPC results, standing-order ledger
        ▼
Observation Reconciler ──► Feature/Vitals/Runway Engine ──► Event Log
        │
        ▼
Objective → Plan → Goal → Task Store ◄──── Strategic Planner
        │                                      │
        ▼                                      └─ proposals only
Attention Scheduler + Lock Arbiter
        │ one focused bounded task
        ▼
Candidate Generator + Hard Validator
        │ offered typed options
        ▼
Decision Router
  ├─ Tier 0: deterministic rule/fallback
  ├─ Tier 1: qualified Laya/Jev/small selector
  ├─ Tier 1.5: optional local judge, row-qualified
  └─ Tier 2: planner escalation on declared triggers
        │ validated intent
        ▼
Single Dispatcher ──► Steward posture / allowlisted workflow / RimBridge
        │
        ▼
Outcome Verifier ──► task transition, lock release, prediction error,
                     failure packet, post-mortem, fixture candidate

Offline or episode-boundary path:
traces → error clusters → reviewer → rimbrain patch → replay/calibration/
matched trials/human gate → signed snapshot → monitored activation/rollback

Export path:
canonical event stream → redaction + projection → portable dataset bundle
```

### 4.1 Runtime model

- One Python process and one `asyncio` event loop are sufficient.
- Reconciliation, scheduling, routing, dispatch, verification, logging, and adapters are isolated services or coroutines behind typed interfaces.
- The dispatcher is one FIFO consumer. It revalidates revisions, locks, freshness, legality, limits, and ownership immediately before a write.
- Provider calls are cancellable, deadline-bound futures. A timeout, invalid response, or stale response routes to deterministic fallback; it is never blindly retried.
- Planning normally occurs while the game is paused. Fast qualified Tier-1 selection normally does not pause.
- A watchdog independent of the framework heartbeat pauses the game if reconciliation stalls while unattended.

### 4.2 Authority table

| Component | Reads game | Chooses policy | Writes game | Changes active brain |
|---|---:|---:|---:|---:|
| RimBridge | Yes | No | Executes validated RPC | No |
| Steward/standing orders | Yes | Fixed policy | Own scope | No |
| Reconciler/features | Yes | No | No | No |
| Scheduler | Derived state | Chooses due task | No | No |
| Tier-1 selector/judge | Bounded packet | One offered option | No | No |
| Planner | Planning packet | Proposes plans/tasks | No | No |
| Reviewer | Saved evidence | Proposes brain patch | No | No |
| Dispatcher | Fresh local state | No | **Only writer** | No |
| Promoter | Evaluation records | Applies declared gates | No | Atomic boundary activation |
| Human operator | Review surfaces | Yes | Controlled override | Yes |

### 4.3 Reconciliation turn

Each wake performs exactly this spine:

1. ingest RimBridge events and Steward ledger changes;
2. refresh only observations needed by due obligations;
3. recompute pawn vitals, site runways, posture, and trend alarms;
4. reconcile pending writes and verify due outcomes;
5. apply emergency and critical-deadline precedence;
6. select one bounded attention item;
7. generate and validate candidates;
8. route to rules, a qualified selector, or a planner trigger;
9. dispatch at most one bounded intent or deliberately wait;
10. persist state and append trace records before acknowledging the turn;
11. schedule the next event-, deadline-, or verification-driven wake.

`awaiting_result` never grants permission to reissue an action.

---

## 5. Survival-first attention and colony control

### 5.1 Lexicographic objective

Alternatives are compared in strict order:

1. **Integrity:** no illegal writes, lost lineage, unowned actions, or uncontrolled game state.
2. **Life:** minimize deaths, near-misses, and time in life-critical states.
3. **Maintenance:** keep health, food, shelter/temperature, power, and safety gates green.
4. **Progress:** achieve verified milestones and the endgame path without stalling.
5. **Efficiency:** reduce model cost, latency, writes, churn, and wall-clock time.

A lower-priority gain cannot compensate for a higher-priority regression. Every episode declares progress floors and records pause ratio so “survive by pausing forever” cannot score well.

### 5.2 Pawn vitals and time-to-critical

Each living pawn has a fresh vital record. Life-critical entries include bleeding, unsafe temperature, starvation, immunity-versus-disease races, infection, toxic exposure, unsafe exhaustion, and dangerous break risk. Each applicable vital exposes a code-computed time-to-critical estimate and known uncertainty.

Rules:

- colony averages never mask pawn-level conditions;
- emergency attention orders by shortest time-to-critical, then deterministic triage value;
- badly calibrated vitals remain `unknown` and trigger observation rather than false precision;
- entry into a life-critical state creates a near-miss event even if the pawn recovers;
- every death and near-miss creates a timeline-based post-mortem and fixture candidate.

### 5.3 Site runway and crisis posture

Runway expresses time or margin to failure for food, medicine, power, freezer integrity, fuel, shelter, temperature, defense readiness, logistics pressure, and per-pawn needs. It is computed per site, including caravans.

Persisted posture uses hysteresis and dwell:

- **GREEN:** gates healthy; surplus may fund progress.
- **AMBER:** warning or pawn TTC below warning horizon; throttle discretionary work and prepare.
- **RED:** failed gate, short TTC, or spiral alarm; pause discretionary goals and focus recovery.
- **BLACK:** simultaneous failures exceed capacity; deterministic, operator-configurable triage doctrine applies.

Every threshold has separate enter and exit bands. Repeated identical action failures trip a circuit breaker. Two or more adverse multi-day trends trigger the spiral detector and one bounded strategic review.

### 5.4 Hard safety invariants

At minimum, validators prevent:

- relying on a downed or life-critical pawn for work or combat;
- risking the only doctor, cook, grower, or other critical role without coverage;
- removing occupied shelter before a verified replacement exists;
- leaving a rescuable downed pawn exposed overnight;
- spending below survival reserves;
- accepting people, quests, or caravans without reserving resulting food, bed, medical, labor, and defense capacity;
- writing while required safety data is stale;
- policy activation during RED/BLACK without operator approval;
- ranked save-scumming or unlabeled intervention.

---

## 6. Planning, tasks, and execution

### 6.1 Core object model

- **Objective:** human-owned desired outcome, constraints, autonomy, risk ceiling, and priority.
- **Plan:** multi-horizon strategy, assumptions, alternatives, milestones, envelopes, predictions, and replan triggers.
- **Goal:** achieve or maintain an observable predicate by a deadline.
- **Task:** one bounded intent instantiated from a registered template.
- **Workflow:** a DAG containing only `observe`, `verify`, `task`, and `wait` nodes.
- **Action template:** typed local implementation with preconditions, limits, ownership, idempotency, and verification.

Task lifecycle:

```text
proposed → ready → running → awaiting_result → succeeded
                    ├─ blocked
                    ├─ suspended
                    ├─ failed
                    └─ cancelled
```

### 6.2 Planner contract

The strategic planner receives a compact, structured packet containing the objective, fresh state, vitals/runways, active incidents, pinned revisions, current plan, relevant capabilities, applicable evidence-backed lessons, resource envelopes, and allowed change scope.

A valid proposal includes:

- explicit assumptions, each linked to an observation and check predicate;
- alternatives considered at a concise claim level;
- measurable goals and an acyclic task graph;
- resource envelopes and critical-role protections;
- success, failure, verification, and replan predicates;
- predicted milestone windows;
- a pre-mortem listing likely lethal failure modes, early warnings, and mitigations;
- an inability or observation request when facts are insufficient;
- a proposed reusable artifact, or an explanation of why this case cannot yet be amortized.

For life-critical or irreversible planning, use a bounded `PLAN → CRITIQUE` sequence. Local schema/reference validation runs after generation; one repair attempt is allowed. Failure retains the last valid plan or pauses according to autonomy policy.

### 6.3 Planner triggers

Tier 2 may run only for:

- episode initialization or adoption of an existing save;
- operator objective or constraint change;
- a violated plan assumption or infeasible goal;
- colonist gain, death, incapacity, or critical capability loss;
- biome, season, technology, site, or threat-profile transition;
- unresolved cross-domain conflict or capability gap;
- repeated failure or prediction-error cluster;
- novel incident with no applicable matrix;
- crisis spiral, milestone completion, scheduled strategic review, or episode review.

Stale observations, transient transport failures, and ordinary blocked actions are handled locally first.

### 6.4 Execution altitude

Prefer the highest sufficient control level:

```text
standing order / Steward posture / stock target
→ persistent policy or threshold bill
→ bounded order or gizmo
→ validated designation, blueprint, or zone
→ direct pawn job only when unavoidable
→ reflective engine write prohibited
```

Fixed phased layout templates precede any general spatial planner. Construction uses `survey → reserve → clear/mine → inspect → shell/utilities → furnish/configure → verify use` and re-estimates after each phase.

### 6.5 Locks

The initial implementation uses expiring, atomically acquired exclusive locks for sites, critical pawn roles, policy objects, and bounded actions. A task acquires all needed locks or none. Only emergencies may revoke locks, and displacement is traced. Quantitative/windowed reservations are deferred until measured contention proves the need.

---

## 7. Tactical decision matrices and model routing

### 7.1 Matrix contract

A matrix attaches to a task template. Each row declares:

- stable `id@revision`, explicit priority, and typed predicates;
- required named features with freshness bounds;
- up to four productive option IDs plus `CONTINUE` and `ESCALATE`;
- deterministic candidate binding to real game objects;
- hard exclusions and safety constraints;
- code-computed cost, risk, duration, and expected-effect fields;
- selector question and comparison criteria;
- deterministic score/fallback;
- action-template mapping, cooldown, timeout, limits, and verifier;
- predicted outcome and verification window;
- selector eligibility and calibration state.

Same-priority multi-match is invalid. Missing critical data routes to observation. Zero legal options routes to escalation or a typed capability gap. One productive option routes deterministically.

### 7.2 Tier-1 qualification

Qualification is **per `(matrix row, selector model revision, prompt/renderer revision)`**, never global.

A selector is live-authorized for a row only when:

1. capability tests enforce schema, offered options, abstention, timeout, and stale-result behavior;
2. replay fixtures meet the declared quality floor against the deterministic baseline;
3. enough context-matched cases exist to estimate calibration honestly;
4. matched development runs show no integrity or maintenance regression;
5. the active pack marks the tuple `qualified`.

Before qualification, the selector may run in shadow mode while rules execute. Calibration or drift regression automatically demotes the row to rules with lineage preserved.

### 7.3 Routing cascade

```text
1. emergency invariant / legality / arithmetic       → Tier 0
2. one productive option or already satisfied       → Tier 0
3. known row, selector tuple qualified               → Laya or Jev
4. selector abstains/times out                       → optional qualified local judge
5. declared novelty/strategic trigger                → Tier 2 planner
6. otherwise                                         → deterministic matrix fallback
```

The optional judge obeys the same offered-option contract and must independently qualify per row. It never becomes an informal second planner.

### 7.4 Provider roles

Required provider-neutral roles:

- `decision_selector`: closed-set `SELECT`; preferred local deployment is Laya, with Jev as an optional hosted adapter;
- `planner`: `PLAN` and `REPAIR` using a capable local or hosted model;
- `reviewer`: `REVIEW_POLICY`, often the same endpoint as the planner but with separate prompt, budget, and revision;
- optional `judge`: closed-set selection after selector abstention;
- `stub_*`: deterministic CI and replay implementations.

Game logic never branches on a vendor or model-family name. Adapters own transport, authentication, cancellation, parsing, and endpoint identity, but cannot change candidate IDs or policy semantics.

### 7.5 Packet discipline and budgets

All packets are rendered by deterministic code from validated fields. Raw transcripts are never used as control input.

- selector: initially ≤1K tokens, one intent, named facts, and offered options;
- judge: initially ≤2K tokens;
- planner/reviewer: initially ≤8K tokens and reduced after measurement;
- every fact includes freshness; every packet has a content hash;
- model requests carry a game-tick deadline; late results are rejected;
- untrusted game/mod text is escaped, length-capped, delimited as data, and cannot originate IDs or parameters;
- prompts and renderers are versioned `rimbrain` artifacts.

Budgets cap calls per game day and episode, repair attempts, tokens, latency, and cost. Budget exhaustion uses deterministic fallback, the current valid plan, or safe pause.

---

## 8. `rimbrain`: human-readable, evolving policy

### 8.1 Definition

`rimbrain` is the complete reusable decision and planning layer, separate from executable engine code and per-episode state. A distributable version of it is a **RimBrain Pack**.

It contains:

| Layer | Format | Purpose |
|---|---|---|
| objectives/plans | YAML | strategy templates, horizons, assumptions, milestones |
| matrices | YAML | bounded tactical decisions and routing eligibility |
| workflows/tasks | YAML | reusable DAGs and typed task templates |
| parameters | YAML | thresholds, hysteresis, budgets, cadence, scoring |
| prompts | Markdown + frontmatter | planner, reviewer, critique, judge contracts |
| knowledge | Markdown + frontmatter | human-readable priors and domain rules |
| lesson snapshot | YAML | reviewed reusable lessons and counterevidence |
| fixtures | JSON | replayable decision, plan, failure, and injection cases |
| schemas/manifest | JSON Schema + YAML | validation, compatibility, hashes, provenance |

Executable Python is not part of an auto-applied pack. New predicates, actions, watchers, or bridge capabilities require normal code review and release.

### 8.2 Canonical layout

```text
rimbrain/
  MANIFEST.yaml
  schemas/
  objectives/
  plans/
  matrices/
  workflows/
  tasks/
  parameters/
  prompts/
  knowledge/rules/
  lessons/snapshot.yaml
  fixtures/{decision,plan,failure,injection}/
  CHANGELOG.md
```

Every executable record has a stable ID and revision. References bind to revisions, never “whatever file is current.” YAML uses a restricted schema: no aliases, unknown execution keys rejected, paths confined to the pack. Markdown is retrieval context, never direct authority.

### 8.3 Evolution model

Three loops remain explicitly separate:

1. **Execution recovery:** refresh, reconcile, retry safely, choose another already-offered method, or block.
2. **Current-colony plan repair:** revise episode tasks, dependencies, locks, predictions, and goals without changing reusable policy.
3. **Reusable brain evolution:** create a pack patch for future episodes.

The always-on micro-loop is:

```text
decision prediction → deterministic outcome verification
→ prediction error → daily context grouping
→ cluster threshold → fixture candidate + review obligation
```

The reusable evolution pipeline is:

```text
error cluster / post-mortem / human insight
→ typed diagnosis with trace references
→ one scoped rimbrain patch
→ schema, reference, DAG, bounds, and security validation
→ append-only fixture ratchet and replay
→ selector/planner calibration gate
→ matched development episodes
→ human approval
→ signed immutable pack snapshot
→ episode-boundary activation
→ monitored cohort
→ retain, demote, or rollback with lineage
```

Active packs never rewrite themselves. Experiment mode may generate proposals, not bypass the pipeline. Bounded parameter autopromotion is deferred until replay and rollback infrastructure is mature, excludes all emergency scopes, and remains constrained to declared safe intervals.

### 8.4 Community distribution and trust

A pack manifest records schema version, semantic version, channel (`dev`, `stable`, `frozen`), compatibility, dependencies, model/prompt expectations, every file hash, authorship, license, provenance, verification suites, and optional signature.

- packs are content-addressed and pinned by manifest hash per episode;
- stable releases change only at episode boundaries;
- unknown authors require explicit local trust and review;
- signatures prove origin, not quality;
- replay fixtures and benchmark evidence establish quality;
- lessons retain support, counterevidence, context, expiry, and provenance;
- removal of a fixture requires a reviewed lineage record;
- community sharing is opt-in and uses sanitized evidence only.

A static signed index is sufficient initially. A marketplace or hosted registry is not required.

---

## 9. Persistence, recovery, and observability

### 9.1 Runtime data layout

```text
runtime/
  state/
    episode.json
    goals.jsonl
    tasks.jsonl
    locks.json
    pending-actions.json
    workflow-cursors.json
    posture.json
  plans/active.yaml
  proposals/<proposal-id>/
  private-lessons/ledger.jsonl
runs/<episode-id>/
  manifest.yaml
  events.jsonl
  observations.jsonl
  attention.jsonl
  decisions.jsonl
  model-calls.jsonl
  actions.jsonl
  outcomes.jsonl
  failures.jsonl
  post-mortems.jsonl
  metrics.jsonl
  final-report.yaml
```

The active `rimbrain` pack is mounted read-only and identified by hash. Runtime state and local private evidence live outside it.

### 9.2 Durability

- Each record includes `schema_version`, stable ID, episode ID, sequence number, game tick, wall timestamp, source, and provenance.
- JSONL is append-only, flushed and `fsync`ed before acknowledgement. A torn final line is recoverable and logged.
- Mutable JSON/YAML state uses sibling temporary files, flush, atomic replace, and best-effort directory sync with tested Windows behavior.
- Each file kind has explicit migrations; loaders reject unknown newer schemas.
- Secrets, absolute local paths, and parent traversal are forbidden in policy, logs, proposals, and exports.
- SQLite, Parquet, and in-memory indexes are derived accelerators only.

### 9.3 Restart sequence

1. validate code/config/pack/schema hashes;
2. load episode, plan, task, lock, posture, and cursor state;
3. query game/save identity and current tick;
4. enter reconcile-only mode;
5. compare pending writes with observed effects;
6. invalidate stale observations and in-flight provider requests;
7. rebuild locks and the attention queue;
8. suspend uncertain ownership or effects;
9. resume writes only after fresh preconditions pass.

Clean shutdown requests game pause, drains or cancels pending work, persists state, then exits. Hard-crash recovery assumes all in-flight effects are uncertain.

### 9.4 Dashboard minimum

The dashboard shall show objective and plan horizons, task graph, attention reason, pawn TTC, site runway, crisis posture, locks, matrix candidates/exclusions, route and fallback, dispatched action, verification status, endpoint health/cost, drift/calibration, pack revision, proposals, and explicit pause/write ownership.

---

## 10. Structured gameplay log export

### 10.1 Purpose

The export interface allows external systems to replay decisions, train bounded selectors or outcome models, analyze strategies, audit model behavior, and compare agents without scraping human prose. Export is local by default and sharing is opt-in.

### 10.2 Canonical event envelope

Every export record uses a common envelope:

```json
{
  "schema_version": 1,
  "event_id": "evt.ep0012.00000421",
  "episode_id": "ep0012",
  "sequence": 421,
  "event_type": "decision.completed",
  "game_tick": 1843200,
  "game_time": {"day": 14, "hour": 6.5},
  "wall_time_utc": "2026-09-22T18:04:03.221Z",
  "source": "decision_router",
  "correlation": {
    "plan_id": "plan.ep0012@4",
    "goal_id": "goal.food.reserve@2",
    "task_id": "task.food.expand.004@1",
    "attempt_id": "attempt.002",
    "request_id": "req.select.0042",
    "parent_event_ids": ["evt.ep0012.00000418"]
  },
  "revisions": {
    "code": "git:<commit>",
    "rimbrain": "sha256:<manifest>",
    "matrix": "matrix.food.planting@2",
    "prompt": "sha256:<prompt>",
    "adapter": "local_structured_http@1",
    "model": "<pinned-model-revision>"
  },
  "payload": {},
  "privacy": {"class": "shareable", "redactions": []}
}
```

Sequence is monotonic within an episode. IDs and parent links form a causal graph; timestamps alone are not used to infer causality.

### 10.3 Required event types

- `episode.started`, `episode.ended`, `episode.intervention`, `episode.reload`;
- `game.event`, `observation.captured`, `feature.computed`, `vitals.updated`, `posture.changed`;
- `plan.requested`, `plan.proposed`, `plan.validated`, `plan.activated`, `plan.repaired`;
- `attention.queued`, `attention.selected`, `attention.preempted`;
- `candidates.generated`, `candidate.excluded`;
- `model.requested`, `model.responded`, `model.rejected`, `model.timed_out`;
- `decision.completed`, `decision.fallback`;
- `action.queued`, `action.dispatched`, `action.result`;
- `verification.scheduled`, `verification.completed`, `prediction.error`;
- `failure.classified`, `near_miss.detected`, `pawn.died`, `post_mortem.completed`;
- `fixture.proposed`, `policy.proposed`, `policy.activated`, `policy.rolled_back`;
- `watchdog.heartbeat`, `watchdog.safe_pause`.

### 10.4 Decision and response payload

A decision export must preserve:

- exact structured observation features and freshness used;
- focused task intent and deadline;
- all candidates offered, deterministic scores, expected costs/risks/effects, and exclusions with reason codes;
- chosen route and why each cascade hop occurred;
- raw provider response only when permitted, plus always a canonical parsed response;
- selected option, deterministic fallback, confidence/probabilities when supplied, and calibration eligibility;
- concise rationale or claims if provided, excluding hidden chain-of-thought;
- final action intent, dispatcher validation result, actual write result;
- predicted result, verification window, observed result, and intervening incidents.

Provider request/response bodies are stored in a restricted local stream. Shared exports default to the canonical structured packet and parsed response, not provider-private reasoning or sensitive headers.

### 10.5 Export bundle

```text
exports/<export-id>/
  MANIFEST.yaml
  DATA_CARD.md
  schemas/*.json
  episodes.jsonl
  events.jsonl
  decisions.jsonl
  trajectories.jsonl
  fixtures/*.json
  reports/metrics.json
  checksums.sha256
```

- **JSONL is canonical** for portability and streaming.
- Optional Parquet projection may be produced for analytics; it is derived and must include the source manifest hash.
- `trajectories.jsonl` provides training-ready windows such as state → candidates → choice → action → delayed outcome, with explicit horizon and censoring fields.
- The manifest records export filters, source episode hashes, schema versions, pack/code/model revisions, game/mod environment, license, assistance flags, and checksums.
- The data card documents collection, intended uses, exclusions, known biases, metric definitions, missingness, censoring, and whether model-generated fields are present.

### 10.6 Export profiles

- `audit-full`: local-only complete canonical records, including endpoint payloads where provider terms allow;
- `analysis`: state, decisions, actions, outcomes, and metrics with private text removed;
- `training`: normalized trajectories, candidate masks, outcomes, split metadata, and leakage controls;
- `community`: aggressively sanitized evidence and benchmark result envelope.

Export supports episode, tick range, event type, domain, matrix row, outcome class, and policy revision filters. Export never modifies source logs.

### 10.7 Privacy, safety, and data quality

Before writing a non-local export:

- remove secrets, auth headers, machine IDs, usernames, absolute paths, and operator-private text;
- pseudonymize pawn and save identifiers consistently within the export;
- mark manual intervention, developer calls, forced reloads, missing events, stale data, and assisted runs;
- preserve rejected and failed decisions to avoid survivorship bias;
- assign train/validation/test splits by start-save family, never by individual correlated decisions;
- keep held-out episodes inaccessible to the learning and review pipeline until retired;
- validate referential integrity, monotonic sequence, schema, checksums, and redaction rules;
- never label unchosen alternatives as failures or fabricate counterfactual rewards.

### 10.8 Export interface

The implementation shall expose a library API and CLI-equivalent contract:

```text
rimagent export --episode <id> --profile analysis --output <dir>
rimagent export --episodes <query> --profile training --split-by start-save-family
rimagent export verify <export-dir>
rimagent replay decisions <export-dir> --rimbrain <pack-ref>
```

Exact command spelling may follow the host CLI, but profile semantics and schemas are stable public interfaces.

---

## 11. Modular repositories and Git submodules

### 11.1 Boundary rule

A component becomes a separate repository or submodule only if it has an independent release cadence, external consumers, a stable protocol, and its own tests. Internal Python packages remain in the runtime repository until those conditions hold. This avoids replacing code coupling with submodule-management overhead.

### 11.2 Recommended superproject

```text
RIMagent/
  runtime/                 # main orchestrator and domain packages
  rimbrain/                # submodule: default human-readable brain pack
  integrations/
    RimBridge/             # upstream/fork submodule pinned to commit
    Steward/               # upstream/fork submodule pinned to commit
  adapters/                # built-in adapters initially; optional repo later
  schemas/                 # public event/export/provider schemas
  tools/
    replay/
    benchmark/
    export/
  ui/
  tests/
  .gitmodules
  versions.lock.yaml       # expected submodule commits + compatibility
```

Recommended independent repositories:

1. **`rimagent-runtime`** — orchestrator, dispatcher, domain code, persistence, and built-in adapters.
2. **`rimbrain-core`** — default pack, prompts, matrices, workflows, fixtures, and changelog; mounted read-only at runtime.
3. **RimBridge** — pinned upstream or project fork only when a required generic capability cannot be contributed upstream.
4. **Steward** — pinned upstream or compatible fork for deterministic work and standing orders.
5. **`rimagent-schemas`** — separate only when external exporter/trainer consumers need independent releases; otherwise keep it in runtime first.
6. **Community brain packs** — separate repositories or signed archives, not branches of runtime code.

Provider adapters should begin in runtime behind entry-point interfaces. Split an adapter into its own repository only when it has heavy optional dependencies or external maintainers.

### 11.3 Interface boundaries

- RimBridge exposes observations/events and executes player-parity actions.
- Steward exposes desired posture, stock/research orders, and an ownership/result ledger.
- Runtime consumes a pinned brain manifest through a read-only `BrainStore` interface.
- Domains register predicates, feature extractors, candidate generators, action templates, and verifiers; they cannot import provider clients or bridge mutation APIs.
- Providers implement typed `Planner`, `Reviewer`, or `Selector` protocols and cannot import the dispatcher.
- Exporters consume the canonical event store, never live service internals.
- UI consumes a read-only query/event API and issues operator commands through an audited control API.

Dependency direction is enforced by import-boundary tests.

### 11.4 Submodule operations

- The superproject pins exact commits; no branch-floating submodules in releases.
- `versions.lock.yaml` duplicates expected component versions and compatibility for clear diagnostics.
- CI initializes submodules recursively, verifies commit/signature policy, then runs contract suites.
- A runtime release records all submodule commits in its build manifest and every episode manifest.
- Brain-pack updates and runtime updates are independent; compatibility is declared and checked before launch.
- Development may use local path overrides, but scored runs reject dirty or unrecorded component states.

---

## 12. Security and trust boundaries

- Credentials use a secret backend and never enter brain files, logs, proposals, model packets, or exports.
- Community packs are untrusted input: restrict paths, reject unknown keys, bound sizes, validate schemas/references/DAGs, and verify hashes/signatures.
- Pack data cannot access RimBridge except through validated runtime action templates.
- Third-party executable extensions require code review, dependency review, sandboxing, and explicit installation; they never auto-apply from a pack.
- Game and mod text is untrusted model input and is escaped and delimited.
- Provider responses are untrusted data until schema, correlation, deadline, offered-option, and revision validation passes.
- Export redaction is allowlist-based for shared profiles.
- The watchdog’s safe state is paused; it cannot dispatch gameplay actions.

---

## 13. Domain implementation order

All domains reuse the same reconcile/attend/route/dispatch/verify/evidence spine.

1. **Landing and survival:** site assessment, pawn roles, equipment, food, first shelter, health policy, stockpile, minimal defense.
2. **Labor and logistics:** critical-role coverage, schedules, storage, hauling, local buffers.
3. **Power, temperature, and production:** generation/storage runway, bills, clothing, equipment, preservation.
4. **Mood and research:** individual causes, recreation/rest, capability graph, useful-unlock verification.
5. **Defense and recovery:** immediate deterministic reflexes from day one; tactical matrix authority only after incident fixtures; every incident includes recovery.
6. **Wealth, trade, recruitment, prisoners, and animals:** utility and survival burden before market value.
7. **Caravans, quests, and multi-site runway:** protect home capacity before departure.
8. **Operator-selected endgame:** long-horizon milestone graph and hazard-aware preparation.

Cross-domain rules include: symptoms link to root-cause tasks; research and expansion consume only verified surplus; recruitment and caravans account for all maintenance consequences; wealth is a threat cost as well as an asset.

---

## 14. Build plan and measurable exits

### Phase 0 — baseline and contracts

Build: pin upstream components; document Windows launch; capture legacy episodes; define typed interfaces, schema repository, environment manifest, and evaluation budget.

Exit: reproducible legacy run, replayable observation capture, measured game-day wall time, and provider stubs passing contract tests.

### Phase 1 — durable shadow spine

Build: event store, migrations, recovery, objective/plan/goal/task models, locks-lite, reconciliation, pawn vitals, runway, posture, scheduler, heartbeat, and dashboard read model. No writes.

Exit: five shadow sessions without framework crash; forced restart preserves lineage; every gate is checked against human-labeled saves; dead-man test pauses the game.

### Phase 2 — dispatcher and deterministic survival

Build: one dispatcher, action templates, idempotency, verification, Steward arbitration, emergency reflex integration, food and shelter workflows, rules selector.

Exit: live three-day landing with zero illegal/unowned writes; all writes verified or honestly failed; restart during an uncertain write causes no duplicate effect.

### Phase 3 — model boundaries and holistic first week

Build: planner/reviewer contracts, Laya and/or Jev adapter, row qualification, shadow selection, prompt packs, packet sanitization, landing planner, health/logistics/basic defense.

Exit: stable matched first week; planner within declared budget; no model can execute unoffered intent; unqualified rows remain rules-only.

### Phase 4 — stable colony maintenance

Build: seasonal forecasts, power/temperature, mood, storage/workshops, production/equipment, research capabilities, hazard outlook, spiral detector, circuit breakers, drift scaffolding.

Exit: 20–30 day matched trials hold all enabled gates and progress floors without earlier-domain starvation.

### Phase 5 — RimBrain Pack and replay

Build: pack manifest, schemas, hashing/signing, read-only mount, diff/pin/verify, proposal workspace, fixture ratchet, decision/plan/failure replay.

Exit: a contributor can fork a pack, add a fixture-backed change, verify it offline, and produce a reviewable signed artifact; no pack code executes.

### Phase 6 — structured export and external use

Build: canonical envelope, event normalization, audit/analysis/training/community profiles, redaction, trajectory generation, data card, checksums, verifier, optional Parquet projection.

Exit: an independent consumer can validate an export, reconstruct decision lineage, replay matrix choices, and train from trajectories without accessing the live agent.

### Phase 7 — broader colony and endgame

Build: trade, recruitment, animals, quests, caravans/site runways, incident recovery, and one victory path.

Exit: safe explainable decisions across matched scenarios and a 60-day holistic pilot with complete lineage.

### Phase 8 — gated self-improvement and community evidence

Build: prediction-error clustering, lesson lifecycle, reviewer patches, calibration ledger, matched trials, monitored promotion/rollback, sanitized benchmark bundles.

Exit: one real repeated failure becomes a fixture-backed proposal that is correctly accepted or rejected; a deliberately bad patch is rejected; a promoted regression rolls back cleanly.

### Phase 9 — optional automation

Build only if evidence warrants it: bounded low-risk parameter promotion, optional judge tier, community index/benchmark aggregation, general spatial planning.

Exit: each optional feature independently beats its simpler baseline and retains a documented kill switch.

---

## 15. Verification and evaluation

### 15.1 Test ladder

1. schema, graph, lifecycle, hysteresis, lock, migration, redaction, and adapter unit tests;
2. recorded observations and provider-malformation fixtures;
3. decision/plan/failure replay;
4. zero-write shadow sessions;
5. short matched landing and maintenance trials;
6. combined 20–30 day trials;
7. matched hazards, combat, and recovery;
8. caravans, seasons, quests, and endgame;
9. rare 60-day pilots;
10. locked held-out evaluation.

### 15.2 Required fixture classes

Include stale/unknown observations; hidden per-pawn crisis; TTC ordering; threshold hysteresis; action acknowledged without effect; timeout with effect already present; duplicate desired states; emergency during model request; malformed/unoffered/late provider response; injection in game text; provider swap in flight; cyclic plan; lock conflict; inaccessible food; season-invalid crop; unenclosed shelter; sole specialist loss; power/freezer failure; wealth without defense; unsafe caravan split; raid recovery; context-mismatched lesson; held-out leakage; torn JSONL; crash with pending action; export redaction and referential integrity.

### 15.3 Metrics

Report in lexicographic order:

1. integrity violations, illegal writes, emergency stalls, reloads, interventions;
2. deaths, survival curves, near-miss duration/rate, TTC margin at response;
3. maintenance runway violations and per-pawn distress;
4. verified progress and progress-floor failures;
5. model calls/cost/latency, pause ratio, actual TPS, game-days per wall-hour, writes and duplicates;
6. deadline misses, blocked duration, plan churn, repeated failures, selector calibration, drift, and trace completeness.

Matched comparisons group uncertainty by start-save family, not by thousands of correlated decisions from one run. Report distributions and limitations; never promote from one anecdotal colony.

---

## 16. Release acceptance criteria

RIMagent is ready for autonomous holistic trials only when all of the following hold.

### Control and survival

- every framework write is attributable to the single dispatcher;
- emergency paths have no provider dependency;
- stale, malformed, unoffered, mismatched, or late model results cannot execute;
- every pawn has freshness-bounded vitals and active TTC where supported;
- AMBER+ attention ordering by TTC is visible in traces;
- hard invariants, hysteresis, dwell, circuit breakers, and watchdog safe-pause pass tests;
- crash recovery reconciles uncertain effects before new work;
- every death and near-miss yields a post-mortem and fixture proposal or a reviewed “not preventable” finding.

### Intelligence and efficiency

- routine pawn work causes zero model calls;
- every planner call maps to a declared trigger;
- every selector-routed row has fixture and calibration qualification;
- rules remain available as immediate fallback;
- plans span immediate, seasonal, strategic, and endgame horizons with falsifiable assumptions and replan triggers;
- planner calls per reusable artifact and per verified milestone are reported.

### Rimbrain and learning

- active policy, prompts, model revisions, and lesson snapshots are frozen and hashed for scored runs;
- a human can edit and review matrices, plans, workflows, prompts, parameters, and knowledge without changing runtime code;
- proposals cannot self-activate;
- fixtures are append-only by default and replayed in CI;
- promotion, demotion, and rollback preserve complete lineage;
- community packs cannot execute code or access secrets.

### Export and external reuse

- a complete episode exports under all permitted profiles;
- schemas, manifest, checksums, data card, revision hashes, assistance flags, and causal links validate independently;
- shared profiles contain no test secrets, credentials, absolute paths, machine IDs, or marked-private operator text;
- external tooling can reconstruct state → candidates → decision → action → outcome trajectories;
- held-out and unchosen-option leakage checks pass;
- raw source logs remain unchanged by export.

### Human reviewability

From the dashboard or export alone, a reviewer can answer:

- What is the colony trying to achieve now and later?
- Which pawn or runway risk has priority, and why?
- Which facts are fresh, stale, or unknown?
- Which options were generated, excluded, offered, and selected?
- Which tier made the decision, and why was that tier eligible?
- What did the dispatcher actually do, and did verification pass?
- Which prompt, model, matrix, pack, lesson, and code revisions were involved?
- What evidence supports or contradicts a proposed improvement?

---

## 17. Final implementation stance

The first vertical slice is a **holistic first week**, not a food-only demo: pause on landing, create a bounded multi-domain plan, let deterministic systems perform routine work, use a qualified small selector only where genuine tactical tradeoffs remain, interrupt safely for emergencies, and verify every material outcome.

The architecture succeeds when larger models are needed less often over time because each useful intervention becomes a human-readable plan, matrix row, workflow, lesson, or fixture in `rimbrain`. It succeeds socially when those artifacts can be forked and improved without trusting executable code. It succeeds scientifically when exported histories let others reproduce decisions, challenge claims, and build better agents from the same evidence.
