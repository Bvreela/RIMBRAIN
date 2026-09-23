# Tasks: Universal Pawn Rules & Start Mode v2

- [x] T148 Contracts review: confirm existing `action.*`/`task.transition` cover universal-rule evidence; add `pawn.assigned` only if a gap is real (FR-901)
- [x] T149 Pack: `equip-pawn`, `wear-apparel`, `assign-job`, `strip-pawn`, `set-plant`, `edit-storage` templates + `universal`/`start.arm`/`start.overflow`/`cooking` config; `pack.schema.json` gains `universal` (FR-905..910)
- [x] T150 `universal.py`: `apply()` — idle-pawn correction, combat target discipline (downed filter, flee-chase), post-round strip; wire into `_run_start`/`run_combat`/`run_loop` after reflexes (FR-901..904)
- [x] T151 `startmode.py` v2: `arm` phase (skill-ranked Equip/Wear), fertile-soil `food` phase (`map.cell` sampling + `set_plant Plant_Rice`), `cookstation`→CookingSpot + TargetCount bill (colonists×meals+buffer), `overflow` phase (second roofed stockpile + `ui.storage` filters) (FR-905..908)
- [x] T152 `combatmode.py`: downed-exclusion in target list, fleeing-chase via melee-capable pawn, strip sweep before heal/restore (FR-903/904)
- [x] T153 Tests: sim gains jobs/idle, weapons/apparel, fertility grid, strip designations; per-FR tests; updated start fixtures (SC-901..905)
- [x] T154 Live validation: idle-poke probe, live combat with strip + downed-switch evidence, full cycle iteration, suite/corpus/validators, docs (INDEX/README/AGENTS)
