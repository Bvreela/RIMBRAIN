"""Fast-evolve play mode (feature 021; ADR-020; FR-2101..2112).

Per in-game day the mode anchors to the autosave nearest day start
(``game.list_saves`` + the pack's ``fastevolve.autosave_pattern``). A
day-failure trigger — pack colony predicates (``fail_when``/
``near_when``) plus the reused goal-level trigger set — pauses the game,
runs a reflection pass (``evolve.maybe_trigger``), promotes any gated
candidate mid-run (``evolve.promote_candidate``), reloads the anchor
through the single-writer dispatch path, and reinitializes run state.

Budget: ``max_reloads_per_day`` (default 2 → 3 attempts/day). An
exhausted day still evolves (per-day pass budget) but never reloads;
the last evolved pack carries forward. The durable day session lives in
``state/fastevolve.json`` — outside RunState, so it survives both the
post-reload wipe and process restarts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import evolve, policy, templates
from .store import write_atomic

SOURCE = "rimbrainagent.runtime.fastevolve"
SESSION_FILE = "fastevolve.json"

DEFAULTS = {
    "max_reloads_per_day": 2,
    "autosave_pattern": r"(?i)autosave",
    "saves_poll_every": 10,
    "max_anchor_age_days": 1,
    "pause_during_evolve": True,
    "max_passes_per_day": 3,
    "triggers": {"use_mutate": True, "fail_when": None, "near_when": None},
}


def cfg_of(pack: dict) -> dict:
    """The pack's ``fastevolve:`` section merged over defaults — absent
    section still yields a runnable config (FR-2110)."""
    cfg = dict(DEFAULTS)
    cfg["triggers"] = dict(DEFAULTS["triggers"])
    for k, v in (pack.get("fastevolve") or {}).items():
        if k == "triggers" and isinstance(v, dict):
            cfg["triggers"].update(v)
        else:
            cfg[k] = v
    return cfg


def can_reload_pack(pack: dict) -> bool:
    """The retry loop needs a ``game.load`` template — a pack without
    one burns attempts on refused loads (e.g. improve-v0's noop set)."""
    return any(t.get("method") == "game.load"
               for t in templates.templates_of(pack)
               if isinstance(t, dict))


def fe_event(event_type: str, payload: dict, seq: int,
             clock=None) -> dict:
    return {
        "schema_version": 0,
        "event_id": f"evt.fe-{seq:06d}",
        "sequence": seq,
        "event_type": event_type,
        "game_tick": None,
        "wall_time_utc": (clock or (lambda: "2026-01-01T00:00:00Z"))(),
        "source": SOURCE,
        "correlation": {},
        "revisions": {"schema_version": 0},
        "payload": payload,
        "privacy": {"classification": "internal", "redactions": []},
    }


class DayState:
    """Durable per-day retry session (data-model: DaySession)."""

    def __init__(self) -> None:
        self.day: int | None = None
        self.day_start_wall: str | None = None
        self.day_start_poll: int = 0
        self.anchor: str | None = None
        self.anchor_day: int | None = None
        self.reloads_used: int = 0
        self.exhausted: bool = False
        self.passes_used: int = 0      # reflection calls this day
        self.attempts: list[dict] = []

    @classmethod
    def load(cls, path: Path) -> "DayState":
        ds = cls()
        try:
            doc = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return ds
        if isinstance(doc, dict):
            ds.day = doc.get("day")
            ds.day_start_wall = doc.get("day_start_wall")
            ds.day_start_poll = int(doc.get("day_start_poll") or 0)
            ds.anchor = doc.get("anchor")
            ds.anchor_day = doc.get("anchor_day")
            ds.reloads_used = int(doc.get("reloads_used") or 0)
            ds.exhausted = bool(doc.get("exhausted"))
            ds.passes_used = int(doc.get("passes_used") or 0)
            ds.attempts = list(doc.get("attempts") or [])
        return ds

    def save(self, path: Path) -> None:
        write_atomic(Path(path), (json.dumps({
            "schema_version": 0,
            "day": self.day,
            "day_start_wall": self.day_start_wall,
            "day_start_poll": self.day_start_poll,
            "anchor": self.anchor,
            "anchor_day": self.anchor_day,
            "reloads_used": self.reloads_used,
            "exhausted": self.exhausted,
            "passes_used": self.passes_used,
            "attempts": self.attempts,
        }, indent=2, sort_keys=True)).encode())


class AutosaveTracker:
    """Throttled ``game.list_saves`` scan; attributes matches to days by
    first-observation order (anchor = earliest first-seen this day = the
    day-start autosave; a later mid-day save never displaces it)."""

    def __init__(self, cfg: dict) -> None:
        self.every = int(cfg.get("saves_poll_every") or 10)
        self.pattern = re.compile(cfg.get("autosave_pattern")
                                  or DEFAULTS["autosave_pattern"])
        self.max_age = int(cfg.get("max_anchor_age_days") or 1)
        self.first_seen: dict[str, tuple[int, int]] = {}  # name->(day,poll)

    def scan(self, game, day: int, poll: int) -> list[str]:
        names = []
        r = game.rpc("game.list_saves")
        res = r.get("result") if r.get("ok") else None
        if isinstance(res, dict):
            res = res.get("saves") or res.get("list") or []
        for row in res or []:
            name = row.get("name") if isinstance(row, dict) else str(row)
            if name and self.pattern.search(name):
                names.append(name)
                self.first_seen.setdefault(name, (day, poll))
        return names

    def anchor(self, session: DayState, names: list[str]) -> tuple:
        """-> (save_name|None, stale:bool). Earliest first-seen match in
        the current day wins; else the newest match not older than
        max_anchor_age_days is a stale fallback."""
        today = [n for n in names
                 if self.first_seen.get(n, (None,))[0] == session.day]
        if today:
            today.sort(key=lambda n: self.first_seen[n][1])
            return today[0], False
        older = sorted(names, key=lambda n: self.first_seen.get(n, (-1, 0)))
        if older:
            day_seen = self.first_seen[older[-1]][0]
            if session.day is not None and day_seen is not None \
                    and session.day - day_seen <= self.max_age:
                return older[-1], True
        return None, False


def check_day_triggers(obs: dict, day_ps, pack: dict,
                       cfg: dict, poll: int) -> tuple:
    """(reason, evidence) — colony predicates first, then the reused
    goal-level trigger set when ``triggers.use_mutate``."""
    trig = cfg.get("triggers") or {}
    ctx = policy.Ctx(cfg=pack, obs=obs, game=None)
    if trig.get("fail_when") and policy.check(trig["fail_when"], ctx):
        return "day_failure", {"predicate": "fail_when"}
    if trig.get("near_when") and policy.check(trig["near_when"], ctx):
        return "day_near_failure", {"predicate": "near_when"}
    if trig.get("use_mutate") and day_ps is not None:
        reason, ev = evolve.check_triggers(day_ps, pack, poll)
        if reason:
            return ("day_failure" if reason == "failure"
                    else "day_near_failure"), ev
    return None, {}


def day_pass_cfg(pack: dict, cfg: dict) -> dict:
    """Day-scoped PassState cfg: mutate: section with the per-day budget
    and no inter-pass cooldown (per data-model — day scope replaces run
    scope)."""
    base = dict(pack.get("mutate") or {})
    base["max_passes_per_run"] = int(cfg.get("max_passes_per_day") or 3)
    base["cooldown_polls"] = 0
    return base


class FastEvolve:
    """Per-run controller; the loop calls :meth:`tick` once per poll."""

    def __init__(self, pack: dict, state_dir: Path, *, clock=None) -> None:
        self.cfg = cfg_of(pack)
        self.state_dir = Path(state_dir)
        self.clock = clock
        self.session = DayState.load(self.state_dir / SESSION_FILE)
        self.tracker = AutosaveTracker(self.cfg)
        self.day_ps = evolve.PassState(day_pass_cfg(pack, self.cfg))
        self._seq = 0

    def note(self, env: dict) -> None:
        """Sink tap — forwards every envelope to the day's PassState."""
        self.day_ps.note(env)

    def note_outcome(self, out: dict | None) -> None:
        self.day_ps.note_outcome(out)

    def note_decisions(self, rows: list) -> None:
        self.day_ps.note_decisions(rows)

    def _emit(self, emit, t: str, payload: dict) -> None:
        self._seq += 1
        if emit is not None:
            emit(fe_event(t, payload, self._seq, self.clock))

    def _persist(self) -> None:
        try:
            self.session.save(self.state_dir / SESSION_FILE)
        except Exception:
            pass

    def view(self) -> dict:
        s = self.session
        return {"day": s.day, "anchor": s.anchor,
                "reloads_used": s.reloads_used,
                "max_reloads": int(self.cfg["max_reloads_per_day"]),
                "exhausted": s.exhausted,
                "passes_used": s.passes_used}

    # -- per-poll driver ----------------------------------------------------

    def tick(self, dispatcher, game, ledger, pack: dict, obs: dict, *,
             tick: int, poll: int, emit=None, pack_id: str | None = None,
             resolver=None, chat=None) -> dict | None:
        """Returns {"reinit": True} when a reload happened — the caller
        performs the brain-reset wipe; ``self.day_ps`` deliberately
        survives (cumulative day evidence)."""
        cfg = self.cfg
        s = self.session
        day = obs.get("day")
        if not isinstance(day, int):
            day = int(obs.get("tick") or 0) // 60000
        rolled = s.day != day
        if rolled:  # rollover: fresh session + budget
            s.day, s.day_start_poll = day, poll
            s.day_start_wall = self.clock() if self.clock else None
            s.anchor, s.anchor_day = None, None
            s.reloads_used, s.exhausted, s.passes_used = 0, False, 0
            s.attempts = []
        if rolled or poll % self.tracker.every == 0:
            names = self.tracker.scan(game, day, poll)
            anchor, stale = self.tracker.anchor(s, names)
            if anchor and anchor != s.anchor:
                s.anchor, s.anchor_day = anchor, day
                self._emit(emit, "fastevolve.day_start",
                           {"day": day, "anchor": anchor,
                            "anchor_stale": stale})
        self._persist()

        reason, evidence = check_day_triggers(obs, self.day_ps, pack,
                                              cfg, poll)
        if reason is None:
            return None
        attempt = {"n": len(s.attempts) + 1, "trigger": reason,
                   "evidence": evidence, "reflect_verdict": None,
                   "candidate_id": None, "reloaded": False,
                   "save": None}
        s.attempts.append(attempt)
        self._emit(emit, "fastevolve.triggered",
                   {"day": day, "attempt": attempt["n"],
                    "reason": reason, "evidence": evidence})

        can_reload = (s.anchor is not None
                      and s.reloads_used < int(cfg["max_reloads_per_day"]))
        if s.anchor is None:
            self._emit(emit, "fastevolve.anchor_missing",
                       {"day": day, "reason": "no autosave match"})
        elif not can_reload:
            if not s.exhausted:
                s.exhausted = True
                self._emit(emit, "fastevolve.exhausted",
                           {"day": day, "attempts": len(s.attempts)})
        # evolve runs regardless (FR-2106: exhausted days still learn),
        # bounded by the per-day pass budget
        verdict = None
        if s.passes_used < int(cfg.get("max_passes_per_day") or 3):
            prev_speed = None
            if cfg.get("pause_during_evolve"):
                st = game.rpc("game.status")
                prev_speed = st.get("result") if st.get("ok") else None
                game.rpc("game.pause", {"paused": True})
            try:
                verdict = evolve.maybe_trigger(
                    self.day_ps, dispatcher=dispatcher, ledger=ledger,
                    pack_loaded=dispatcher._pack
                    or {"pack": pack, "hash": ""},
                    pack=pack, pack_id=pack_id
                    or dispatcher._pack_file or "?",
                    state_dir=self.state_dir, tick=tick, poll=poll,
                    fair=getattr(dispatcher, "_fair", True),
                    emit=emit or (lambda e: None), clock=self.clock,
                    resolver=resolver, chat=chat, force=reason)
            except Exception as exc:
                self._emit(emit, "fastevolve.triggered",
                           {"day": day, "attempt": attempt["n"],
                            "reason": "pass_error",
                            "evidence": {"error": str(exc)[:200]}})
            finally:
                if prev_speed is not None:
                    game.rpc("game.speed",
                             {"speed": prev_speed.get("speed", 0)})
                    game.rpc("game.pause",
                             {"paused": bool(prev_speed.get("paused"))})
            s.passes_used += 1
        attempt["reflect_verdict"] = (verdict or {}).get("verdict")
        attempt["candidate_id"] = (verdict or {}).get("path") and \
            Path(verdict["path"]).stem

        if can_reload:
            promoted = self._promote(dispatcher, pack_id, emit)
            if promoted:
                self._emit(emit, "fastevolve.promoted",
                           {"day": day, "candidate_id": promoted,
                            "parent_hash": None})
            res = dispatcher.dispatch("load-game", {"name": s.anchor})
            attempt["reloaded"] = bool(res.get("ok"))
            attempt["save"] = s.anchor
            s.reloads_used += 1  # a failed load still spends the attempt
            if res.get("ok"):
                from .phase import _wait_playing
                _wait_playing(game)
                self._emit(emit, "fastevolve.reloaded",
                           {"day": day, "attempt": attempt["n"],
                            "save": s.anchor,
                            "candidate_id": attempt["candidate_id"]})
        self._persist()
        return {"reinit": attempt["reloaded"]}

    def _promote(self, dispatcher, pack_id: str | None, emit) -> str | None:
        """Install the pending candidate mid-run (ADR-020) and rebind the
        dispatcher's hash so pack_drift stays sound."""
        pid = pack_id or dispatcher._pack_file
        if not pid:
            return None
        rows = evolve.lineage_rows(self.state_dir)
        pending = next((r for r in reversed(rows)
                        if r.get("target_pack") == pid
                        and r.get("state") == "pending"), None)
        if not pending:
            return None
        res = evolve.promote_candidate(
            Path(pending.get("candidate_path") or ""), pending, pid,
            self.state_dir, fair=getattr(dispatcher, "_fair", True),
            mid_run=True, emit=emit, clock=self.clock)
        if not res.get("ok"):
            return None
        dispatcher.load_pack(pid)  # rebind hash — drift stays intact
        return pending["candidate_id"]
