# Data ownership and persistence contract

**Status:** READY

## 1. Storage roots

```text
<install>/                      immutable installed component code
<config>/                       operator config and secret references
<packs>/<pack-hash>/            immutable validated RimBrain snapshots
<state>/<instance>/             mutable runtime state
<runs>/<episode>/               canonical append-only episode evidence
<proposals>/<proposal>/         mutable review workspace, never active
<cache>/                        disposable indexes/captures
<exports>/<export>/             immutable derived bundles
```

Paths are configurable and need not live inside a source checkout. Development defaults may use the superproject root, but releases must distinguish them.

## 2. Ownership table

| Data | Owner | Writers | Readers | Mutation model |
|---|---|---|---|---|
| component code | component repo | human/build | runtime/build | release immutable |
| release profile | superproject | release process | all | immutable version |
| active pack | RimBrain release | pack release | runtime/lab/dashboard | immutable mount |
| config | operator | operator/config tool | runtime/deploy | atomic replace |
| secrets | secret backend | operator | adapters only | backend-defined |
| episode state | runtime store | store commands | runtime/read API | atomic snapshot + journal |
| canonical events | runtime event store | event sink only | runtime/lab/dashboard | append-only |
| private endpoint payloads | runtime restricted store | provider service | audit-full local only | append-only/retention |
| proposal workspace | proposal service/human | validated proposal tools | lab/dashboard/human | reviewed mutable |
| private lessons | local operator/runtime | evidence loop/reviewer proposal | planner review | append/status revisions |
| export | Lab | exporter | external tools | immutable after seal |
| dashboard cache | dashboard | dashboard | dashboard | disposable |
| lab indexes | Lab | Lab | Lab | disposable |

## 3. Canonical versus derived

Canonical:

- active release/pack identity;
- runtime state snapshots/journals;
- raw normalized observations and source event references;
- decisions, requests/results, actions, verifications, failures, interventions;
- human/operator commands and approvals.

Derived:

- UI read models;
- BM25/SQLite/Parquet indexes;
- summaries and metric aggregates;
- trajectory projections;
- calibration/drift reports;
- semantic diffs.

Derived data includes source hashes and can be deleted/rebuilt.

## 4. Write protocol

### Append-only JSONL

1. validate record against pinned schema;
2. assign monotonic sequence under event-store lock;
3. serialize canonical JSON without NaN/Infinity;
4. append one line;
5. flush and `fsync` file before acknowledging;
6. publish in-memory/SSE projection only after durable append.

On load, only a malformed final partial line may be truncated automatically. Emit a recovery event with original file/hash/offset. Mid-file corruption is fatal and triggers safe pause.

### Mutable snapshots

1. validate complete candidate object;
2. write sibling temporary file;
3. flush and sync;
4. atomically replace target;
5. sync directory when supported;
6. record snapshot revision event.

Windows behavior and antivirus/file-sharing failures receive dedicated tests and bounded retry; failure never falls back to truncating the target.

## 5. Recovery data

Persist at minimum:

- game/save identity and last observed tick/event sequence;
- controller/evaluation modes and independent pause states;
- objective, active plan and revisions;
- goals/tasks/lifecycle attempts;
- locks and expirations;
- pending actions, idempotency keys, target/effect ownership;
- verification schedules/windows;
- workflow cursors;
- posture/hysteresis/dwell state;
- provider requests in flight (invalidated on restart);
- active release/pack/schema revisions;
- heartbeat and clean-shutdown marker.

## 6. Revision and lineage

Every record references exact code/release/pack/matrix/prompt/adapter/model/observation revisions applicable to it. Lineage edges are stable IDs, not filenames. A label can change without breaking lineage.

## 7. Retention

- Canonical scored episode records are never automatically deleted.
- Local non-scored raw provider payloads have configurable retention.
- Closed run logs may be compressed only with manifest/checksum update and transparent reader support.
- Caches may use size/age eviction.
- Exports have explicit retention and sharing consent.
- Deletion tools require operator action and never delete source as a side effect of export.

## 8. Privacy classes

- `public-policy`: intended pack content.
- `shareable`: sanitized gameplay facts/metrics.
- `pseudonymous`: stable export-local IDs.
- `operator-private`: messages, private notes, paths.
- `restricted-provider`: raw request/response where terms/privacy require local handling.
- `secret`: never permitted in canonical records.

Every event/export field inherits or declares a class. Shared profiles use allowlists, not denylist-only scrubbing.

## 9. Consistency and clocks

Game tick is the gameplay ordering clock. Episode sequence is the durable event ordering clock. UTC wall time supports operations only. Causal parent IDs express causality. Never infer causal order solely from wall timestamps or thread completion.

## 10. Migration

Each file kind has explicit one-step migrations. Upgrade procedure backs up/snapshots, migrates between scored series, validates/replays, and records old/new hashes. Loaders refuse unknown newer versions and do not guess.
