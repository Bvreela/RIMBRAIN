# Requirements traceability matrix

**Status:** READY  
**Rule:** This matrix is updated with concrete test/report links during implementation.

| Requirement set | Owning component | Primary work packages | Required evidence |
|---|---|---|---|
| UR-CTL-001..002 | Runtime | WP-100, WP-200, WP-201 | import/capability audit; action log writer identity |
| UR-CTL-003..004 | Contracts, Runtime | WP-002, WP-201 | schema tests; dispatcher validation fixtures |
| UR-CTL-005..008 | Runtime, Steward | WP-103, WP-200, WP-203, WP-402 | emergency no-provider audit; stale result and controller isolation tests |
| UR-RUN-001..004 | Runtime | WP-101, WP-102, WP-104 | forced crash/recovery and lifecycle fixtures |
| UR-RUN-005..007 | Runtime | WP-103, WP-400 | dead-man, circuit breaker, hysteresis/dwell tests |
| UR-RUN-008 | Runtime, Contracts | WP-301 | cancel/timeout/stale correlation fixtures |
| UR-SUR-001..004 | Runtime | WP-103, WP-400, WP-600 | labeled-save TTC/runway/site fixtures |
| UR-SUR-005..006 | Runtime, RimBrain | WP-103, WP-203, WP-300 | posture transitions; dispatcher invariant rejection |
| UR-SUR-007 | Runtime, Lab | WP-202, WP-400, WP-501 | death/near-miss post-mortem fixture creation |
| UR-SUR-008..009 | Lab, Runtime | WP-400, WP-601 | lexicographic report; progress/pause/stall results |
| UR-MOD-001..003 | Runtime, Contracts | WP-301 | provider swap and closed-choice tests |
| UR-MOD-004..005 | Runtime, Lab, RimBrain | WP-302, WP-601 | row qualification/calibration/demotion/fallback fixtures |
| UR-MOD-006 | Runtime | WP-303 | planner-trigger audit |
| UR-MOD-007..008 | Runtime, Contracts | WP-301, WP-303 | packet budget/freshness/hash/injection fixtures |
| UR-MOD-009..010 | Runtime, RimBrain | WP-303 | proposal schema, pre-mortem, critique, repair tests |
| UR-BRN-001..003 | RimBrain, Contracts | WP-300 | pack validation/reference/canonicalization tests |
| UR-BRN-004..006 | Runtime, RimBrain | WP-300, WP-602 | scored freeze, proposal isolation, atomic activation/rollback |
| UR-BRN-007..009 | RimBrain, Lab | WP-300, WP-501, WP-602 | hash/signature/trust and fixture-ratchet CI |
| UR-BRN-010 | Runtime, Lab | WP-202, WP-602 | 100% due predictions scored/clustered without model call |
| UR-BRN-011..014 | Runtime, RimBrain, Contracts | feature 012 (T155..T162), ADR-015 | `policy.py` engine + pack-driven start/combat/universal; pack-mutation tests (SC-1001..1003); `validate_policy` fail-closed; `policy_version` in pack schema; live: pack-driven start mode completed all exit conditions on a real colony (shelter/beds/food/meals/recreation), pack idle-rule assigned real jobs |
| UR-DAT-001..003 | Runtime, Contracts | WP-101 | durability/torn-tail/atomic Windows tests |
| UR-DAT-004..005 | Runtime, Lab | WP-104, WP-202, WP-500 | complete decision projection; unchosen-label check |
| UR-DAT-006 | All | WP-002, WP-300, WP-500 | secret/path scans and malicious pack/export cases |
| UR-DAT-007 | Runtime, Lab, Dashboard | WP-101, WP-500, WP-502 | rebuild-from-canonical tests |
| UR-EXP-001..004 | Lab, Contracts | WP-500 | schema-valid profile and trajectory golden tests |
| UR-EXP-005..008 | Lab | WP-500 | redaction, checksum, data card, assistance, split leakage, immutability tests |
| UR-EXP-009 | Lab | WP-500, WP-501 | independent verifier/reconstruction/replay report |
| UR-ARC-001 | All | WP-000, WP-100 | dependency graph/static import tests |
| UR-ARC-002 | Superproject | WP-000 | clean recursive checkout/release manifest check |
| UR-ARC-003 | RimBridge, Steward, Runtime | WP-203, WP-402 | capability-gap review and bridge policy scan |
| UR-ARC-004 | Contracts, all consumers | WP-002 onward | shared corpus provider/consumer CI |
| UR-ARC-005 | Superproject, Steward | WP-000, WP-402 | license/notice audit |
| UR-ARC-006 | Superproject | all | work-package gates and this matrix |
| UR-ARC-007 | Dashboard, Lab | WP-500, WP-502 | no-internal-import/direct-control tests |
| UR-ARC-008 | Superproject, Runtime | WP-000, WP-601 | ranked dirty-state rejection fixture |

## Acceptance scenario trace

| Scenario | Requirements demonstrated | Planned rung |
|---|---|---|
| Forced crash after uncertain write | CTL-004/006, RUN-003/004, DAT-001..003 | integration fault injection |
| Bleeding pawn during provider timeout | CTL-005, SUR-001..003, MOD-005 | emergency fixture + live bounded scenario |
| Laya returns unoffered option late | CTL-006, RUN-008, MOD-003/005 | provider contract fixture |
| Cold snap invalidates crop plan | SUR-004/005, MOD-006/009, BRN-003 | replay + matched scenario |
| Community pack path escape/tamper | BRN-007/008, DAT-006 | pack security test |
| Export training split leakage | EXP-004..007 | export golden/privacy test |
| Dashboard resume with independent hold | CTL-007, ARC-007 | API/UI E2E |
| Pack regression after activation | BRN-004..006/009 | monitored cohort rollback exercise |

## Evidence format

Each implemented row eventually links:

- component version/commit;
- test ID and CI run artifact;
- fixture/save family/hash;
- result summary and date;
- known limitations/waivers;
- approving reviewer for human gates.

No requirement moves to `IMPLEMENTED` from code presence alone.
