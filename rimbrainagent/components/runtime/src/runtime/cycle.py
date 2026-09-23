"""Save-reset improvement cycle (feature 010): iterated training loop.

Per iteration: load checkpoint -> wait until playing -> run_start ->
run_combat -> run_improve -> emit `cycle.completed`. The checkpoint is
created once (game.save) before the loop and reloaded every iteration so
each cycle faces the identical world state — honest cross-cycle evidence.

Each cycle gets its own ledger/mode-state dir (`state/cycle-N/`): after a
reload the colony is fresh again, so task/mode state must reset while
canonical events (events.jsonl, feed.md) keep accumulating globally.
"""

from __future__ import annotations

import time
from pathlib import Path

from .combatmode import _wait_playing, run_combat
from .improve import run_improve
from .startmode import run_start
from .tasks import TaskLedger


def _saves(game) -> list[str]:
    r = game.rpc("game.list_saves")
    res = r.get("result") if r.get("ok") else None
    if isinstance(res, dict):
        res = res.get("saves") or res.get("list") or []
    return [s.get("name") if isinstance(s, dict) else str(s)
            for s in (res or [])]


def completed_event(iteration: int, checkpoint: str, phases: dict,
                    ticks: int, seq: int, clock) -> dict:
    return {
        "schema_version": 0,
        "event_id": f"evt.cycle-{seq:06d}",
        "sequence": seq,
        "event_type": "cycle.completed",
        "game_tick": None,
        "wall_time_utc": (clock or (lambda: "2026-01-01T00:00:00Z"))(),
        "source": "rimbrainagent.runtime.cycle",
        "correlation": {},
        "revisions": {"schema_version": 0},
        "payload": {"iteration": iteration, "checkpoint": checkpoint,
                    "phases": phases, "ticks": ticks},
        "privacy": {"classification": "internal", "redactions": []},
    }


def run_cycle(dispatcher, game, pack: dict, store, *,
              iterations: int = 2, sink=None, clock=None,
              speed: int | None = 3, state_root: Path | None = None) -> dict:
    """cfg sections come from the loaded pack: start/combat/improve/cycle."""
    cycle_cfg = pack.get("cycle") or {}
    checkpoint = cycle_cfg.get("checkpoint", "rimbrain-cycle")
    order = cycle_cfg.get("order") or ["start", "combat", "improve"]
    emit = sink or getattr(dispatcher, "_sink", None)
    root = Path(state_root) if state_root else Path(
        getattr(store, "path", Path("state") / "events.jsonl")).parent

    results = []
    # checkpoint exists? create once via the dispatcher (FR-805)
    if checkpoint not in _saves(game):
        dispatcher.dispatch("save-game", {"name": checkpoint})
    for i in range(iterations):
        t0 = time.monotonic()
        phases = {}
        # per-cycle state namespace: fresh colony == fresh ledger
        cdir = root / f"cycle-{i:03d}"
        cdir.mkdir(parents=True, exist_ok=True)
        ledger = TaskLedger(cdir / "tasks.jsonl",
                            sink=getattr(dispatcher, "_sink", None))
        if "start" in order:
            dispatcher.dispatch("load-game", {"name": checkpoint})
            _wait_playing(game)
            res = run_start(dispatcher, game, ledger, pack,
                            iterations=int(cycle_cfg.get(
                                "start_iterations", 400)),
                            sink=sink, clock=clock, speed=speed,
                            hold=False)  # bounded phase: hand off to combat
            phases["start"] = ("completed" if res.get("completed")
                               else "incomplete")
        if "combat" in order:
            res = run_combat(dispatcher, game, ledger, pack,
                             iterations=int(cycle_cfg.get(
                                 "combat_iterations", 400)),
                             sink=sink, clock=clock, speed=speed,
                             mode_state_dir=cdir)
            phases["combat"] = res.get("verdict") or (
                res.get("error", {}).get("code", "failed"))
        if "improve" in order and store is not None:
            res = run_improve(store, pack.get("improve") or {},
                              active_pack=pack, iterations=1,
                              sink=sink)
            cyc = (res.get("cycles") or [{}])[-1]
            phases["improve"] = cyc.get("verdict", "noop")
        ticks = int(time.monotonic() - t0)
        seq = getattr(dispatcher, "_events", 0) + 1
        env = completed_event(i, checkpoint, phases, ticks, seq, clock)
        if emit is not None:
            emit(env)
        results.append({"iteration": i, "phases": phases,
                        "ticks": ticks})
    return {"ok": True, "iterations": results, "checkpoint": checkpoint}
