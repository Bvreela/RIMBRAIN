# Repository and submodule topology

**Status:** READY  
**Requirements:** UR-ARC-001..008

## 1. Superproject role

`rimbrainagent` is a release and integration superproject. It pins component revisions, carries cross-component specifications, defines compatible version sets, and runs contract/acceptance orchestration. It does not become a dumping ground for runtime logic.

## 2. Prepared layout

```text
rimbrainagent/
  .gitmodules
  AGENTS.md
  README.md
  upstream/
    rimagent/                 # actual pinned upstream baseline submodule
      mod/                    # upstream's nested RimBridge submodule
  components/
    contracts/                # future submodule
    runtime/                  # future submodule
    rimbrain/                 # future submodule
    steward/                  # future submodule
    lab/                      # future submodule
    dashboard/                # future submodule
  integrations/
    rimbridge/                # future direct pinned submodule
  specs/
    00-foundation/
    10-architecture/
    20-submodules/
    30-contracts/
    40-work-packages/
    50-verification/
    90-decisions/
    templates/
  profiles/                   # release-compatible component/model profiles
  deploy/                     # deployment manifests/instructions, no secrets
  tests/
    contract/
    fixtures/
    acceptance/
```

The prepared component directories contain only placeholder README files. They are replaced by real Git submodules after remote repositories exist.

## 3. Future Git topology

| Path | Remote class | Versioning | Initial source |
|---|---|---|---|
| `components/contracts` | project-owned | SemVer; schema compatibility policy | new extraction |
| `components/runtime` | project-owned fork | SemVer | fork `zorrobyte/rimagent` Python agent |
| `components/rimbrain` | project-owned/community-forkable | pack SemVer + manifest hash | migrate settings/brain knowledge |
| `components/steward` | project-owned fork | SemVer + RimWorld compatibility | extract upstream `mod-steward` history/content |
| `components/lab` | project-owned | SemVer | extract/replace SFT export and add replay/eval |
| `components/dashboard` | project-owned | SemVer | extract upstream FastAPI dashboard UI |
| `integrations/rimbridge` | upstream or narrow fork | pinned commit/release | `zorrobyte/rimbridge` |
| `upstream/rimagent` | upstream read-only | pinned commit | baseline evidence only |

## 4. Why these are submodules

- **Contracts:** independent consumers in Python, C#, UI, and external training tools.
- **Runtime:** deployable without community policy history or evaluation tooling.
- **RimBrain:** high-frequency community policy changes without runtime releases.
- **Steward:** RimWorld mod build/release cadence differs from Python runtime.
- **Lab:** large optional analytics dependencies and offline-only trust boundary.
- **Dashboard:** independent frontend release and read/control protocol.
- **RimBridge:** already independent generic upstream project.

Provider adapters and gameplay domains remain packages inside runtime initially. They do not yet justify repository-level fragmentation.

## 5. Bootstrap sequence once remotes exist

1. Create project-owned repositories with licenses and branch protection.
2. Import or extract history where practical; preserve attribution.
3. Add component remotes as exact-path submodules.
4. Add direct RimBridge integration submodule.
5. Remove the nested `mod` dependency from the runtime fork after build scripts consume `integrations/rimbridge`.
6. Keep `upstream/rimagent` for comparison until the migration reaches framework default; it may later move to release tooling or be removed by ADR.
7. Add `versions.lock.yaml` only when real component versions exist.
8. Commit submodule pointers and release profile together.

## 6. Release profile

A profile eventually records:

```yaml
profile_schema: 1
release: rimbrainagent-0.1.0
components:
  contracts: {version: 0.1.0, commit: <sha>}
  runtime: {version: 0.1.0, commit: <sha>}
  rimbrain: {version: 0.1.0, manifest_sha256: <hash>, commit: <sha>}
  steward: {version: 0.1.0, commit: <sha>}
  lab: {version: 0.1.0, commit: <sha>}
  dashboard: {version: 0.1.0, commit: <sha>}
  rimbridge: {version: 0.1.0, commit: <sha>}
compatibility:
  rimworld: "1.6.x"
  python: ">=3.12,<3.13"
```

This is an illustrative contract, not a file to execute yet.

## 7. Build order

1. contracts validation and generated bindings;
2. RimBridge;
3. Steward against RimBridge DLL/contracts;
4. runtime against contracts;
5. dashboard and lab against contracts;
6. RimBrain pack validation;
7. integration contract suites;
8. deployment assembly;
9. shadow/live acceptance suites.

## 8. Submodule rules

- Pin commits; never release branch-floating pointers.
- No local filesystem URLs.
- Component release tags are signed where governance supports it.
- CI verifies submodule commit allowlists and recursively clean state.
- Dirty components are allowed only in labeled development runs.
- A superproject release changes pointers and compatibility profile atomically.
- Security fixes remain component commits; the superproject only consumes them.

## 9. Root ownership

The root owns only specifications, release profiles, deployment composition, cross-component fixtures, and acceptance orchestration. Component-specific unit tests and implementation docs stay with their component.
