"""Feed tests (feature 009; FR-805, SC-803)."""

from __future__ import annotations

from runtime.audit import DECISION_TYPES, audit_ux
from runtime.feed import FeedWriter, render_event


def _env(t, payload=None, eid="evt.t-1", tick=10):
    return {"event_type": t, "event_id": eid, "game_tick": tick,
            "payload": payload or {}}


def test_every_decision_type_renders():
    for t in DECISION_TYPES:
        line = render_event(_env(t, {"template_id": "x",
                                     "task_id": "t", "cycle_id": "c",
                                     "check_id": "k", "domain": "code",
                                     "verdict": "pass",
                                     "candidate_id": "c1",
                                     "gate": "metrics", "reasons": ["r"],
                                     "episode_id": "e"}))
        assert line and line != f"{t}: {{}}"


def test_unknown_type_falls_back_to_echo():
    assert "weird.type" in render_event(_env("weird.type", {"a": 1}))


def test_feed_writer_keys_entries_to_event_ids(tmp_path):
    feed = FeedWriter(tmp_path / "feed.md")
    feed.write(_env("action.issued", {"template_id": "haul"}, "evt.1"))
    feed.write(_env("task.transition",
                    {"task_id": "t1", "to_state": "succeeded"}, "evt.2"))
    text = (tmp_path / "feed.md").read_text()
    assert "evt.1" in text and "evt.2" in text
    assert "haul" in text and "succeeded" in text


def test_feed_write_failure_is_not_fatal(tmp_path):
    feed = FeedWriter(tmp_path / "no" / "such" / "deep" / "feed.md")
    feed.write(_env("action.issued"))  # parent dirs missing -> swallowed


def test_ux_audit_full_coverage(tmp_path):
    feed = FeedWriter(tmp_path / "feed.md")
    events = [_env(t, {"template_id": "x", "task_id": "t",
                       "cycle_id": "c", "check_id": "k",
                       "domain": "code", "verdict": "pass",
                       "candidate_id": "c1", "gate": "metrics",
                       "reasons": ["r"], "episode_id": "e",
                       "error": {"code": "e", "message": "m"}},
                   eid=f"evt.{i}")
              for i, t in enumerate(sorted(DECISION_TYPES))]
    for e in events:
        feed.write(e)
    v = audit_ux(tmp_path / "feed.md", events)
    assert v["verdict"] == "pass"
    assert v["details"]["missing_entries"] == 0


def test_ux_audit_flags_missing_entry(tmp_path):
    feed = FeedWriter(tmp_path / "feed.md")
    events = [_env("action.issued", {"template_id": "x"}, "evt.1"),
              _env("action.completed", {"template_id": "x"}, "evt.2")]
    feed.write(events[0])  # evt.2 never narrated
    v = audit_ux(tmp_path / "feed.md", events)
    assert v["verdict"] == "fail"
    assert "evt.2" in v["reasons"][0]
