"""Metrics tests (feature 009; FR-807, SC-805)."""

from __future__ import annotations

from runtime.metrics import episode_metrics, metrics_event


def _ep(refused=0, issued=10, succeeded=3, failed=0, ticks=(0, 100)):
    evs = [{"event_type": "action.issued", "sequence": i,
            "game_tick": ticks[0] + i, "payload": {}}
           for i in range(issued)]
    evs += [{"event_type": "action.refused", "sequence": 100 + i,
             "game_tick": ticks[1], "payload": {}}
            for i in range(refused)]
    for i, st in enumerate(["succeeded"] * succeeded +
                           ["failed"] * failed):
        evs.append({"event_type": "task.transition",
                    "sequence": 200 + i, "game_tick": ticks[1],
                    "payload": {"to_state": st, "task_id": f"t{i}"}})
    return evs


def test_deterministic():
    evs = _ep(refused=2)
    assert episode_metrics(evs) == episode_metrics(list(evs))


def test_two_histories_differ():
    good = episode_metrics(_ep(refused=0, succeeded=5))
    bad = episode_metrics(_ep(refused=5, failed=2, succeeded=1))
    assert good["refusal_rate"] < bad["refusal_rate"]
    assert good["task_completion_rate"] > bad["task_completion_rate"]


def test_rates():
    m = episode_metrics(_ep(refused=2, issued=10, succeeded=3, failed=1))
    assert m["refusal_rate"] == 0.2
    assert m["verify_failure_rate"] == 0.25
    assert m["task_completion_rate"] == 0.75
    assert m["ticks_to_baseline"] == 100
    assert m["event_span"]["count"] == 16


def test_empty_episode():
    m = episode_metrics([])
    assert m["refusal_rate"] == 0.0
    assert m["ticks_to_baseline"] is None


def test_metrics_event_shape():
    env = metrics_event(_ep(), "ep-1", seq=7)
    assert env["event_type"] == "episode.metrics"
    assert env["sequence"] == 7
    assert env["payload"]["episode_id"] == "ep-1"
