"""Visible spine demo (features 004/006/007): one objective lives through the
ledger while the sim colony runs.

    observe -> reconcile -> attend(reflex) -> dispatch -> verify -> evidence

Run:  uv run --with pyyaml python tools/demo_spine.py
Sim only; never touches the bridge. Artifacts land in state/.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "components" / "runtime" / "src"))
sys.path.insert(0, str(REPO / "components" / "contracts" / "src"))

import shutil

from runtime.dispatch import Dispatcher
from runtime.simgame import SimGame
from runtime.store import EventStore
from runtime.tasks import TaskLedger

state_dir = REPO / "state"
shutil.rmtree(state_dir, ignore_errors=True)

events = EventStore()                     # state/events.jsonl
game = SimGame()
d = Dispatcher(game, sink=events.append,
               clock=lambda: "2026-01-01T00:00:00Z")
d.load_pack("core-survival-v0")
ledger = TaskLedger(sink=events.append)   # transitions join the event stream

ITERS = 5
print(f"{'tick':>5} | {'fires':>5} {'downed':>6} | "
      f"{'task state':>11} | events this poll")
print("-" * 72)

for i in range(ITERS):
    state = game.rpc("game.status")["result"]
    tick = state["tick"]
    n0 = ledger._events + d._events

    # 1. RECONCILE — re-verify open work against observed state
    r = ledger.reconcile(state, tick)

    # 2. ATTEND — deterministic reflexes (fire/rescue) still run via pack
    d.reflex(state)

    # 3. objective arises from observation: fire seen -> propose task
    fire_task = "task.extinguish-fire"
    if state["map"]["fires"] > 0 and fire_task not in ledger.tasks:
        ledger.propose({
            "task_id": fire_task, "kind": "firefight",
            "action": {"template_id": "firefight",
                       "params": {"pawn": "Gomez", "job": "Firefight",
                                  "target": [10, 10]}},
            "resources": ["pawn:Gomez"],
            "effect": {"field": "map.fires", "op": "eq", "value": 0},
            "lease_ticks": 60, "max_attempts": 3}, tick=tick)

    # 4. ROUTE/DISPATCH — push the task through the single writer
    t = ledger.tasks.get(fire_task)
    if t and t["state"] == "proposed":
        ledger.acquire(fire_task, tick)
    if t and t["state"] == "locked":
        res = d.dispatch(t["action"]["template_id"],
                         dict(t["action"]["params"]))
        ledger.mark_dispatched(fire_task, ok=bool(res.get("ok")), tick=tick)
    elif t and t["state"] in ("dispatched", "verifying"):
        # 5. VERIFY — success only when the world shows it
        ledger.verify(fire_task, state, tick)

    new = [e["event_type"] for e in
           events.load()["events"][-(ledger._events + d._events - n0):]
           ] if ledger._events + d._events > n0 else []
    st = ledger.tasks.get(fire_task, {}).get("state", "-")
    print(f"{tick:>5} | {state['map']['fires']:>5} "
          f"{state['colonists']['downed']:>6} | {st:>11} | "
          + ", ".join(new))
    game.advance(i)

print("-" * 72)
print(f"tasks.jsonl:  {ledger._path} "
      f"({len(ledger._store.load()['events'])} transitions)")
for f in ("cursor.json", "locks.json", "events.jsonl"):
    p = state_dir / f
    if p.exists():
        print(f"{f:>13}:  {json.loads(p.read_text()) if f != 'events.jsonl' else str(sum(1 for _ in p.open())) + ' events'}")
