# Implementation Plan: Universal Pawn Rules & Start Mode v2

**Feature**: `011-universal-pawn-rules` | **Status**: Draft

## Approach

1. **Contracts (T148)** — no new event types needed: all universal-rule actions ride existing `action.issued/completed/failed/refused` + `task.transition`. Update `start.completed` schema is NOT required (exit conditions unchanged in count; `meals` already added by 010). Corpus unchanged.
2. **Pack (T149)** — new templates: `equip-pawn` (`ui.job` Equip), `wear-apparel` (`ui.job` Wear), `assign-job` (`ui.job` generic), `strip-pawn` (`ui.designate` strip), `set-plant` (`ui.zone` set_plant), `edit-storage` (`ui.storage`), `create-growing` (if missing). New pack config: `universal` (idle job fallback list, chase rules, strip toggle), `start.arm` (skill→role mapping), `start.cooking` buffer fields, `start.overflow` config. `pack.schema.json` gains `universal`.
3. **`universal.py` (T150)** — `apply(obs, dispatcher, cfg, context)`: (a) idle check over `obs` colonists (job field from `state.pawns`/`state.pawn`), dispatch first untried fallback job with a real target; (b) combat discipline: filter downed from attack list, chase fleeing with melee-capable pawn; (c) post-round strip designations. Wired into `_run_start`, `run_combat`, `run_loop` poll loops.
4. **`startmode.py` v2 (T151)** — new phases: `arm` (skill-ranked equip), `overflow` (second zone+roof+filters); upgrade `food` phase to fertile-cell rice (`map.cell` sampling + `set_plant`); upgrade `cookstation` to `CookingSpot` + `TargetCount` bill = colonists×meals+buffer.
5. **`combatmode.py` (T152)** — downed filtering, flee-chase orders, post-round strip before heal/restore.
6. **Tests (T153)** — sim: jobs/idle flag, weapons/apparel defs, fertility grid, strip designations; tests per requirement.
7. **Live validation (T154)** — idle-poke probe, live combat with strip evidence, full cycle iteration, suite/corpus/validators, docs sync.

## Invariants

- Single writer: every universal-rule action is a dispatched pack template.
- Fail-closed: missing skills/jobs/fertility fields → rule defers, never guesses.
- Universal rules never precede emergency reflexes (caller order fixed).
- Bounded: per-poll work is O(colonists + hostiles + small cell grid).

## Live-probe checklist

- `state.pawns`/`state.pawn` field for current job/idle.
- `map.cell` fertility field name + scale.
- `ui.designate strip` on downed hostile vs corpse.
- `ui.job Equip/Wear` param shape (`target` = thing id).
- `ui.storage` allow/disallow arg shape (`zone` label vs id).
