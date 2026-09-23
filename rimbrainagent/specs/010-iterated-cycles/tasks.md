# Tasks: Iterated Improvement Cycles

- [x] T141 Contracts: `combat.completed` + `cycle.completed` schemas, event-map entries, corpus valid/invalid (FR-801/803/804)
- [x] T142 Pack: save/load/incident/draft/attack/heal/add-bill templates + `cooking`, `combat`, `cycle` config; pack schema gains `combat`/`cycle` properties (FR-801/802/805/806)
- [x] T143 `startmode.py`: `cookstation` + `meals` baseline phases, `meals` exit condition, bill add after station observed (FR-802, FR-807)
- [x] T144 `combatmode.py`: prereq check, snapshot, bounded incident rounds, draft/attack defense, clear+survive verify, heal+restore, `combat.completed` (FR-803, FR-806)
- [x] T145 `cycle.py` + CLI `--mode combat|cycle`: checkpoint once, load+wait-playing per iter, start→combat→improve ordering, `cycle.completed` (FR-801/804)
- [x] T146 Tests: sim extensions (cooking/bills/meals/hostiles), combat tests, cycle tests, updated start-mode fixtures (SC-801..805)
- [x] T147 Live validation: real cycle iteration; suite + corpus + validators; docs (INDEX/README/AGENTS)
