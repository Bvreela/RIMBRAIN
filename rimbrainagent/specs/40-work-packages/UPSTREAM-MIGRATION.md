# Upstream migration map

**Status:** READY  
**Baseline:** upstream RimAgent `85cb050`

## 1. Migration strategy

Use strangler-style migration:

1. pin/reproduce upstream;
2. create explicit controller boundary;
3. add canonical contracts/events without changing legacy behavior;
4. run framework shadow beside legacy observations, not writes;
5. enable one dispatcher/domain at a time;
6. extract independently versioned repositories after interfaces stabilize;
7. make framework default only after measurable exits;
8. retain legacy as opt-in recovery/baseline until a later removal ADR.

## 2. File-by-file Python disposition

| File/area | Action | Target | Key constraint |
|---|---|---|---|
| `agent/pyproject.toml` | modify | runtime packaging | rename/metadata only with compatibility CLI; add dependencies through package manager |
| `rimagent/cli.py` | adapt | runtime `cli/` | preserve upstream commands; add controller/profile/pack/verify commands |
| `config.py` | replace behind compatibility loader | runtime config | typed deep merge, secret refs, unknown-key rejection |
| `paths.py` | replace | runtime paths | no import-time writes; separate install/config/state/run/cache/export roots |
| `runner.py` | split | `legacy/controller.py`, `app/lifecycle.py`, framework services | preserve legacy logic; no incremental “if framework” maze in one 800-line class |
| `loop.py` | retain/extract | legacy loop + bridge observation adapters | no free-form think in framework |
| `context.py` | retain legacy | legacy only | framework role-scoped deps replace shared bridge+LLM context |
| `bridge.py` | split | read/mutation gateways | mutation gateway constructible only by dispatcher composition |
| `llm.py` | wrap/retain | legacy adapter + provider adapters | role-specific configs, deadlines, identity; capture to canonical events |
| `registry.py` | retain legacy; new explicit registries | policy/execution | dynamic tools not available in framework |
| `roles.py` | legacy only | optional read advisers later | no parallel write streams in framework |
| `bus.py` | adapt | observability projection | canonical event store writes first |
| `memory.py` | legacy only | structured store replaces authority | notebook may remain operator view |
| `reflect.py` | split | legacy reflection + proposal service | no framework hot edits/commits |
| `braingit.py` | legacy/pack tooling separation | RimBrain/Lab | runtime active pack read-only |
| `watchers.py` | classify | legacy or typed alerts | no framework Python watcher writes |
| `watchdog.py`, tools | development legacy | separate dev profile | disabled in ranked; never live deploy |
| `tracker.py`, `worlddiff.py` | extract useful pure reads | feature/observation | version formulas and freshness |
| `scorecard.py` | retain legacy | Lab metrics replaces framework evaluation | wealth not optimized scalar |
| `export_sft.py` | legacy adapter | Lab | label incomplete lineage; no default chain-of-thought export |
| `dashboard/app.py` | compatibility API then extract | dashboard | remove direct paths/git/bridge imports |
| `tools/*` | retain legacy | explicit framework controls/actions elsewhere | no unrestricted rpc/run_python |
| `knowledge/*` | retain input | RimBrain knowledge/Lab cache | policy provenance and evidence status |
| `tests/*` | preserve + reorganize | runtime tests | baseline green before behavior changes |

## 3. Steward extraction

Source: `mod-steward/` including About metadata, source, tests, notices, build assumptions.

Sequence:

1. capture RPC/event golden fixtures;
2. create standalone repo preserving history if practical;
3. make RimBridge reference path configurable;
4. pass original tests unchanged;
5. integrate Contracts capability/version schema;
6. add compatible intent correlation/idempotency;
7. update root build order and runtime gateway;
8. remove embedded copy only after release artifact parity.

## 4. RimBridge handling

Do not migrate code into project repositories. Add direct submodule after component remotes exist. Runtime fork initially may retain its nested pointer for legacy build; deployment chooses one canonical checkout and rejects duplicate loaded mods. Any bridge change starts with capability-gap evidence and a generic upstream proposal.

## 5. Brain/settings migration

| Upstream/current artifact | Destination | Initial status |
|---|---|---|
| `brain/skills/*.md` | RimBrain knowledge cards | source prior/hypothesis |
| `brain/tools/*.py` | legacy only or reviewed runtime action/helper | never auto-pack |
| `brain/watchers/*.py` | legacy only; behavior mapped to Steward/typed alerts | never auto-pack |
| notebook | runtime episode/operator view | nonauthoritative prose |
| journal | private lesson import candidates | unproven |
| scores | legacy evidence adapter | scalar not promotion authority |
| root `settings/*.yaml` examples | RimBrain typed content | validate/revise, not assumed executable |
| guidance Markdown | prompt pack | version/hash/replay required |

## 6. Runtime compatibility milestones

- **M0:** upstream tests/build reproduced and artifacts hashed.
- **M1:** `legacy` controller behavior/CLI parity in fork.
- **M2:** canonical event mirroring observes legacy without affecting it.
- **M3:** framework shadow produces task/attention/decision traces.
- **M4:** dispatcher controls food/shelter desired states; legacy writes disabled in framework.
- **M5:** framework default after first-week matched exit.
- **M6:** dashboard/Steward/Lab extracted and legacy adapters isolated.

## 7. Data migration

Never rewrite upstream evidence in place. Import creates new canonical records with `source_format`, source file/hash/offset, incomplete-field flags, and generated import ID. Legacy events lacking game ticks/revisions remain incomplete and cannot qualify selector rows or policy promotion unless manually supplemented with verified provenance.

## 8. Rollback

Each milestone retains:

- previous release profile/submodule pointers;
- state schema backup/migration reversal policy;
- active pack pointer snapshot;
- controller mode switch requiring safe shutdown/restart;
- documented unsupported downgrade if state has crossed an irreversible schema boundary.

Rollback does not rewrite episode history; it starts a new run/recovery record with lineage.
