# Configuration and RimBrain pack contract

**Status:** READY

## 1. Configuration layers

Lowest to highest precedence:

1. compiled safe defaults;
2. release profile defaults;
3. system config;
4. user-local config;
5. explicit CLI overrides;
6. audited runtime operator commands for allowed ephemeral fields.

Merge behavior is schema-defined per field. Unknown keys are errors in framework mode. Secrets use references resolved by adapters; `${ENV}` may configure nonsecret deployment fields but resolved secret values never enter effective-config dumps.

## 2. Configuration groups

- `controller`: legacy/framework and autonomy mode.
- `evaluation`: normal/experiment/ranked, assistance/reload policy.
- `paths`: pack/state/run/cache/export/proposal roots.
- `bridge`: URL, timeouts, expected capabilities/revision.
- `steward`: expected protocol, enable/order desired state.
- `providers`: role-to-adapter configurations and secret refs.
- `budgets`: calls/tokens/cost/latency/repair limits.
- `runtime`: wake/heartbeat/recovery/durability settings.
- `policy`: active pack ref/hash and qualification snapshot.
- `dashboard`: bind/port/control policy.
- `export`: local retention/default profile only; sharing remains explicit.

## 3. Validation

Startup validates:

- allowed mode combination;
- path confinement/writability and separate active/proposal roots;
- release profile and submodule/build identity;
- contracts and pack compatibility;
- bridge/Steward capability reports;
- role adapter capability tests or declared disabled roles;
- budget and timeout consistency;
- ranked cleanliness, pinned model revisions, pack hash, and no forbidden features;
- required emergency/reflex capability before autonomous mode.

Failure is explicit and occurs before write authority is enabled.

## 4. Example effective intent

```yaml
controller:
  mode: framework
  autonomy: shadow
  evaluation: development
policy:
  pack: rimbrain.core-survival@0.1.0
  manifest_sha256: sha256:<pinned>
providers:
  decision_selector:
    adapter: laya
    endpoint: http://127.0.0.1:9000
    model_revision: <pinned>
    fallback: rules
  planner:
    adapter: openai_chat_completions
    endpoint: ${PLANNER_BASE_URL}
    model_revision: ${PLANNER_MODEL_REVISION}
    secret_ref: secret:RIMBRAIN_PLANNER_KEY
budgets:
  planner: {calls_per_game_day: 2, calls_per_episode: 30, repair_attempts: 1}
```

Illustrative only; Contracts owns final schema.

## 5. Pack manifest

Required manifest fields:

- schema/manifest version;
- pack ID, SemVer, channel, parent/provenance;
- authors/license/source;
- game/DLC/mod/runtime/contracts/RimBridge/Steward compatibility;
- dependency pack IDs/version ranges;
- exact file paths, sizes, hashes, and kinds;
- prompt/renderer identities;
- selector qualification references;
- fixture suites and validation tool versions;
- build/release time and optional signature.

No unpinned network reference is execution authority. Registry URLs locate artifacts only; manifest hashes authenticate content.

## 6. Pack loading

1. resolve local artifact by reference;
2. verify archive/path safety and size limits;
3. parse restricted YAML/Markdown frontmatter;
4. validate manifest and every file schema;
5. verify hashes/signature/trust policy;
6. resolve dependencies and compatibility;
7. build canonical registry and resolve all references;
8. validate matrices, DAGs, thresholds, bounds, prompts, and fixtures;
9. materialize immutable content-addressed snapshot;
10. return `BrainSnapshot` identity; do not mutate source.

Pack classes (UR-BRN-018): every pack declares `class: fair|dev`. A fair-class pack contains zero `dev.*` bridge methods and is the only kind loadable under a fair/ranked run — the loader refuses a dev-class pack (`pack.not_fair`) before write authority exists, so debug tooling is absent from the registry rather than merely refused at dispatch. Optional pack sections by role: `start`/`govern` (bootstrap + standing post-start goals), `goal_options` (inert strategy option space), `improve`, `combat`/`cycle` (dev-class scripting only), `universal`.

## 7. Activation

Activation is a command against a validated snapshot. Preconditions: allowed mode/boundary, no RED/BLACK unless explicit operator approval, current pointer revision matches, rollback snapshot exists, release/profile compatibility passes, and no pending action depends on changed semantics. Activation atomically changes pointer, emits lineage event, and starts monitoring cohort.

## 8. Proposal workspace

A proposal has parent manifest hash, one scope, changed/new/deleted objects, diagnosis/evidence refs, expected effect, risk class, fixtures, validation reports, author/reviewer, and status. Runtime reviewers can write only through proposal API. Deleting fixtures, changing hard constraints, schemas, evaluator, verifier semantics, or executable IDs requires human/code review and may be outside pack scope.

## 9. Semantic diff

Diff reports object-level effects rather than only text:

- added/removed/revised IDs;
- condition/priority overlap changes;
- offered/fallback/action/verifier changes;
- threshold/hysteresis/budget changes;
- workflow graph changes;
- prompt hash and fixture behavior changes;
- lesson support/counterevidence/status changes;
- routes whose selector eligibility changes.

## 10. Scored-run freeze

Episode manifest stores effective config hash, release profile, component commits, contracts version, pack manifest hash, qualification snapshot, prompt/model/adapter identities, environment/save hash, and assistance policy. Runtime refuses mid-episode activation or mutable/unpinned components in ranked mode.
