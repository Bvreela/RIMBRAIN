# Release acceptance gates

**Status:** READY

## Gate A — Repository integrity

- recursive submodules initialized and clean;
- component commits match release profile;
- licenses/notices present;
- no secrets or local filesystem submodule URLs;
- contracts/pack/build hashes reproducible;
- supported toolchain/environment recorded.

## Gate B — Contracts

- schemas and valid/invalid corpus pass;
- provider/consumer contract tests pass for every included component;
- no undeclared breaking contract change;
- migration path exists for supported prior versions;
- event type/interface catalogs match implementations.

## Gate C — Control safety

- audit proves one framework writer;
- no provider-bearing service can call mutation gateway;
- emergency tests contain no provider dependency;
- stale/malformed/unoffered/mismatched/late results never execute;
- operator/game/dispatcher holds are independent and restart-safe;
- high-impact actions honor approval policy.

## Gate D — Durability and recovery

- acknowledged event/state writes survive forced termination;
- torn final append recovers with explicit event;
- mid-file corruption fails closed;
- uncertain action reconciles before retry/new work;
- pack/release/game identity mismatch blocks unsafe resume;
- clean shutdown pauses and persists.

## Gate E — Survival and stability

- every living pawn has fresh vitals for supported conditions;
- AMBER+ ordering by TTC is trace-visible;
- site runways and posture transitions satisfy fixtures;
- every threshold has hysteresis; dwell/churn/circuit breakers enforced;
- dead-man safe pause works while framework is hung;
- death/near-miss post-mortems and fixture obligations are complete.

## Gate F — Model routing

- deterministic rules available for every row;
- selector routes only qualified tuples;
- demotion/fallback works without restart where specified;
- every planner call maps to declared trigger/budget;
- packets meet freshness, budget, hash, and injection rules;
- planner assumptions, predicates, verification, predictions, and pre-mortem validate.

## Gate G — RimBrain

- active pack immutable and content-addressed;
- all references, matrices, DAGs, thresholds, prompts, fixtures validate;
- proposal cannot self-activate;
- fixture suite did not shrink without approved lineage;
- activation/rollback exercised at safe boundary;
- no auto-executed code or secret in pack.

## Gate H — Export and external reuse

- each allowed profile exports and independently verifies;
- causal lineage reconstructs state→choice→action→outcome;
- redaction corpus finds no prohibited data;
- training splits are family-disjoint and unchosen options unlabeled;
- assistance/missingness/censoring/rejections are preserved;
- source logs unchanged; manifest/data card/checksums complete.

## Gate I — Human reviewability

Dashboard/export answers:

- current and future objective;
- attention reason and competitors;
- pawn/site risk and freshness;
- generated/excluded/offered/selected options;
- tier eligibility and fallback reason;
- dispatched write and ownership;
- verification result and intervening incidents;
- exact component/pack/prompt/model revisions;
- evidence supporting/contradicting a proposal.

## Gate J — Phase outcome

Release demonstrates the phase-specific measurable exit in `IMPLEMENTATION-PLAN.md`, reports eval budget consumed, known failures, guardrail outcomes, and kill-criterion status. Passing engineering tests without the phase outcome is not sufficient for autonomous authority.

## Approval record

A release acceptance record lists every gate as pass/fail/not-applicable with evidence URI/hash, reviewer, date, waivers, and expiration. Safety, integrity, privacy, and contract violations cannot be waived for ranked/autonomous release.
