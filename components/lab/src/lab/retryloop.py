"""Checkpoint-reload retry-loop engine + CLI (feature 003, T051; FR-201..210).

Loop semantics (specs/003-checkpoint-retry):

1. Guard: refuse to start while a scored episode is active -- a flag passed by
   the caller or a truthy ``scored_episode_active``/``scored`` in
   ``game.status`` -- hard rejection, no events (FR-208).
2. Save a namespaced checkpoint ``<family>--<run_id>--cp<N>``, verified via
   ``game.list_saves`` before and after (FR-206).
3. Per window (1-based ``iteration``; iterations >= 2 are retries): advance
   ``window_ticks`` at the configured ``speed``, evaluate the gate over the
   observed state, then:

   - gate pass -> ``early_exit`` (FR-203);
   - gate fail + retries remain -> pop exactly one mutation, apply it to the
     candidate (invalid -> reject, keep prior revision, FR-204), reload the
     checkpoint, verify tick/day via ``game.status`` (FR-210), next window;
   - gate fail + cap reached or mutation space empty -> ``exhausted``.

4. Hard bounds: ``max_retries`` (retries AFTER the first attempt, so total
   windows <= max_retries + 1), ``budgets.per_window_s``, ``budgets.total_s`` --
   exceeding any aborts with a named error, never a hang (FR-207, SC-204).
5. Every iteration emits canonical ``retry.*`` envelopes (FR-205): see
   ``EVENT_TYPES``. ``episode_id``/``revisions`` are null when unknown -- never
   fabricated (R5); event ids are ``evt.retry-<seq:06d>``.

CLI::

    python -m lab.retryloop --config X.yaml --mode sim|live [--bridge URL]
        [--run-id run.X] [--episode-id ep.X] [--export DIR]
        [--scored-episode-active]

``contracts``/``jsonschema`` are soft-optional: config schema validation runs
when both are importable (tests supply them via ``uv run --with``); otherwise a
structural check enforces the same required keys.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from lab.bridge import (
    TICKS_PER_DAY,
    GameCtl,
    LiveBridge,
    ManualClock,
    SimBridge,
    error_envelope,
)
from lab.gate import GateError, evaluate
from lab.mutations import MutationSpace

__all__ = [
    "EVENT_TYPES",
    "SCHEMA_VERSION",
    "SOURCE",
    "TICKS_PER_HOUR",
    "RetryConfigError",
    "checkpoint_name",
    "load_config",
    "run_loop",
    "window_ticks_of",
    "main",
]

SCHEMA_VERSION = 0
SOURCE = "lab.retryloop"
TICKS_PER_HOUR = 2500  # RimWorld: 2500 ticks per game-hour

EVENT_TYPES = {
    "checkpoint_saved": "retry.checkpoint.saved",
    "window_started": "retry.window.started",
    "gate_evaluated": "retry.gate.evaluated",
    "mutation_applied": "retry.mutation.applied",
    "iteration_completed": "retry.iteration.completed",
    "loop_completed": "retry.loop.completed",
}

_CONFIG_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "contracts"
    / "schemas"
    / "runtime"
    / "retry-config.schema.json"
)

_REQUIRED_CONFIG_KEYS = (
    "schema_version",
    "config_id",
    "max_retries",
    "speed",
    "checkpoint_family",
    "gate_ref",
    "mutation_space_ref",
    "budgets",
)


class RetryConfigError(ValueError):
    """Raised when a retry config fails contract/structural validation."""


# ---------------------------------------------------------------------------
# config loading (T046 contract consumer)
# ---------------------------------------------------------------------------


def window_ticks_of(config: dict) -> int:
    """Resolve the configured window to ticks (2500 ticks per game-hour)."""
    if "window_ticks" in config:
        return int(config["window_ticks"])
    return int(round(float(config["window_hours"]) * TICKS_PER_HOUR))


def checkpoint_name(family: str, run_id: str, index: int) -> str:
    """Namespaced save name: ``<family>--<run_id>--cp<N>`` (FR-206)."""
    return f"{family}--{run_id}--cp{index}"


def _structural_check(config: Any) -> list[str]:
    """Minimal offline check used when jsonschema/the schema is unavailable."""
    errors = []
    if not isinstance(config, dict):
        return ["config is not a mapping"]
    for key in _REQUIRED_CONFIG_KEYS:
        if key not in config:
            errors.append(f"missing required key {key!r}")
    has_ticks = "window_ticks" in config
    has_hours = "window_hours" in config
    if has_ticks == has_hours:
        errors.append("exactly one of window_ticks / window_hours is required")
    budgets = config.get("budgets")
    if isinstance(budgets, dict):
        for key in ("per_window_s", "total_s"):
            if key not in budgets:
                errors.append(f"budgets is missing {key!r}")
    return errors


def _schema_errors(config: dict) -> list[str] | None:
    """Validate against the JSON-Schema contract when jsonschema + the schema
    file are available; returns ``None`` when the strict path is unavailable
    (caller falls back to the structural check)."""
    if not _CONFIG_SCHEMA_PATH.is_file():
        return None
    try:
        import jsonschema
        from referencing import Registry, Resource
        from referencing.jsonschema import DRAFT202012
    except ImportError:
        return None
    schemas_dir = _CONFIG_SCHEMA_PATH.parents[1]  # components/contracts/schemas
    resources = []
    for path in sorted(schemas_dir.rglob("*.schema.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        resources.append(
            (doc["$id"], Resource.from_contents(doc, default_specification=DRAFT202012))
        )
    registry = Registry().with_resources(resources)
    schema = json.loads(_CONFIG_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema, registry=registry)
    return sorted(
        f"{'/'.join(str(p) for p in e.absolute_path) or '/'}: {e.message}"
        for e in validator.iter_errors(config)
    )


def load_config(path: str | Path) -> dict:
    """Load and validate a RetryConfig YAML file against the contract schema."""
    path = Path(path)
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RetryConfigError(f"{path}: not valid YAML: {exc}") from exc
    if not isinstance(config, dict):
        raise RetryConfigError(f"{path}: config must be a YAML mapping")

    errors = _schema_errors(config)
    if errors is None:
        errors = _structural_check(config)
    if errors:
        raise RetryConfigError(
            f"{path} rejected by runtime/retry-config: " + "; ".join(errors)
        )
    return config


# ---------------------------------------------------------------------------
# engine
# ---------------------------------------------------------------------------


def _rfc3339(epoch_s: float) -> str:
    return (
        datetime.fromtimestamp(epoch_s, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _default_run_id(config: dict) -> str:
    config_id = str(config.get("config_id", "rl.run"))
    slug = config_id.split(".", 1)[-1]
    return f"run.{slug}"


def _scored_active(status: dict) -> bool:
    return bool(status.get("scored_episode_active") or status.get("scored"))


def run_loop(
    config: dict,
    bridge: GameCtl,
    *,
    scored_episode_active: bool = False,
    episode_id: str | None = None,
    run_id: str | None = None,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    sink: Callable[[dict], None] | None = None,
) -> dict:
    """Run one checkpoint-retry loop; returns the run-result dict.

    ``result["events"]`` is the ordered list of canonical ``retry.*`` envelopes;
    ``result["iterations"]`` the per-window records (SC-203 attribution).
    """
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    run_id = run_id or _default_run_id(config)
    config_id = config.get("config_id")

    events: list[dict] = []
    iterations: list[dict] = []
    last_tick: int | None = None
    parent_event: str | None = None
    pre_state: dict | None = None  # {speed, paused} captured at loop start (T056)

    def emit(event_type: str, payload: dict, game_tick: int | None = None) -> dict:
        nonlocal parent_event, last_tick
        if game_tick is None:
            game_tick = last_tick
        envelope = {
            "schema_version": SCHEMA_VERSION,
            "event_id": f"evt.retry-{len(events) + 1:06d}",
            "episode_id": episode_id,
            "sequence": len(events) + 1,
            "event_type": event_type,
            "game_tick": game_tick,
            "wall_time_utc": _rfc3339(clock()),
            "source": SOURCE,
            "correlation": {"parent_event": parent_event},
            "revisions": {"schema_version": SCHEMA_VERSION},
            "payload": payload,
            "privacy": {"classification": "internal", "redactions": []},
        }
        parent_event = envelope["event_id"]
        events.append(envelope)
        if sink is not None:
            sink(envelope)
        return envelope

    def _restore() -> dict | None:
        """Restore pre-run speed/pause once (T056); None when nothing to do."""
        nonlocal pre_state
        if pre_state is None:
            return None
        pre, pre_state = pre_state, None  # restore at most once, any exit path
        errs: list[str] = []
        if pre.get("speed") is not None:
            r = bridge.set_speed(int(pre["speed"]))
            if not r.get("ok"):
                errs.append(f"set_speed: {r['error']['code']}")
        if pre.get("paused"):
            r = bridge.pause()
            if not r.get("ok"):
                errs.append(f"pause: {r['error']['code']}")
        return None if not errs else {"ok": False, "errors": errs}

    def finish(outcome: str, reason: str, error: dict | None, mutations_applied: int) -> dict:
        restore = _restore()
        payload: dict[str, Any] = {
            "run_id": run_id,
            "outcome": outcome,
            "iterations": len(iterations),
            "max_retries": config["max_retries"],
            "mutations_applied": mutations_applied,
            "reason": reason,
        }
        if restore is not None:
            payload["restore_error"] = restore["errors"]
        if error is not None:
            payload["error"] = {"code": error["code"], "message": error["message"]}
        emit(EVENT_TYPES["loop_completed"], payload)
        return {
            "ok": outcome != "aborted",
            "run_id": run_id,
            "config_id": config_id,
            "outcome": outcome,
            "reason": reason,
            "error": error,
            "checkpoint": checkpoint_record,
            "window_ticks": window_ticks,
            "max_retries": config["max_retries"],
            "speed": config["speed"],
            "iterations": iterations,
            "events": events,
            "candidate": candidate,
        }

    def abort(reason: str, code: str, message: str, mutations_applied: int,
              details: dict | None = None) -> dict:
        restore = _restore()
        err = error_envelope(code, message, details=details)["error"]
        if restore is not None:
            err["details"] = dict(err.get("details") or {})
            err["details"]["restore_error"] = restore["errors"]
        return finish("aborted", reason, err, mutations_applied)

    # -- structural config check (run() also validates callers' dicts) -------
    config_errors = _structural_check(config)
    if config_errors:
        return {
            "ok": False,
            "error": error_envelope(
                "retry.config.invalid",
                "; ".join(config_errors),
                details={"errors": config_errors},
            )["error"],
            "events": [],
            "iterations": [],
            "run_id": run_id,
        }

    window_ticks = window_ticks_of(config)
    max_retries = int(config["max_retries"])
    speed = int(config["speed"])
    family = str(config["checkpoint_family"])
    per_window_s = float(config["budgets"]["per_window_s"])
    total_s = float(config["budgets"]["total_s"])
    gate_ref = str(config["gate_ref"])
    candidate = deepcopy(config.get("candidate") or {})
    checkpoint_record: dict[str, Any] | None = None
    mutations_applied = 0

    # -- guard: scored-episode hard rejection (FR-208) ------------------------
    if scored_episode_active:
        return {
            "ok": False,
            "error": error_envelope(
                "retry.scored_episode_active",
                "retry loops are forbidden while a scored episode is active",
            )["error"],
            "events": [],
            "iterations": [],
            "run_id": run_id,
        }

    status = bridge.status()
    if not status.get("ok"):
        return {
            "ok": False,
            "error": error_envelope(
                "retry.status.unavailable",
                "game.status unavailable at loop start",
                details={"bridge_error": status.get("error")},
            )["error"],
            "events": [],
            "iterations": [],
            "run_id": run_id,
        }
    observed = status["result"]
    pre_state = {
        "speed": observed.get("speed"),
        "paused": bool(observed.get("paused")),
    }
    if _scored_active(observed):
        return {
            "ok": False,
            "error": error_envelope(
                "retry.scored_episode_active",
                "game.status reports an active scored episode",
            )["error"],
            "events": [],
            "iterations": [],
            "run_id": run_id,
        }
    if observed.get("state") != "playing":
        return {
            "ok": False,
            "error": error_envelope(
                "retry.game.not_playing",
                f"game is not in 'playing' state: {observed.get('state')!r}",
            )["error"],
            "events": [],
            "iterations": [],
            "run_id": run_id,
        }

    gate_def = config.get("gate")
    if not isinstance(gate_def, dict):
        return {
            "ok": False,
            "error": error_envelope(
                "retry.config.gate_unresolved",
                f"gate_ref {gate_ref!r} has no embedded gate definition in config",
            )["error"],
            "events": [],
            "iterations": [],
            "run_id": run_id,
        }
    space = MutationSpace(config.get("mutation_space") or [])
    total_deadline = clock() + total_s

    # -- checkpoint: namespaced save, verified via list_saves (FR-206) --------
    cp_index = 0
    save_name = checkpoint_name(family, run_id, cp_index)
    pre = bridge.list_saves()
    if not pre.get("ok"):
        result = abort(
            "bridge_error", "retry.saves.unavailable",
            "game.list_saves failed before checkpoint",
            mutations_applied, details={"bridge_error": pre.get("error")},
        )
        return result
    saved = bridge.save(save_name)
    if not saved.get("ok"):
        return abort(
            "bridge_error", "retry.checkpoint.save_failed",
            f"game.save {save_name!r} failed",
            mutations_applied, details={"bridge_error": saved.get("error")},
        )
    post = bridge.list_saves()
    names = [e.get("name") for e in (post.get("result") or [])] if post.get("ok") else []
    if save_name not in names:
        return abort(
            "bridge_error", "retry.checkpoint.verify_failed",
            f"checkpoint {save_name!r} not present in game.list_saves after save",
            mutations_applied,
        )
    checkpoint_record = {
        "save_name": save_name,
        "family": family,
        "tick": observed.get("tick"),
        "day": observed.get("day"),
    }
    last_tick = observed.get("tick") if isinstance(observed.get("tick"), int) else None
    emit(
        EVENT_TYPES["checkpoint_saved"],
        {
            "run_id": run_id,
            "checkpoint_id": f"cp{cp_index}",
            "save_name": save_name,
            "family": family,
            "tick": checkpoint_record["tick"],
            "day": checkpoint_record["day"],
        },
        game_tick=last_tick,
    )

    # -- window loop ----------------------------------------------------------
    retries_used = 0
    last_mutation_id: str | None = None
    iteration = 0
    while True:
        if clock() > total_deadline:
            return abort(
                "budget_total", "retry.budget.total",
                f"total budget {total_s}s exceeded before window {iteration + 1}",
                mutations_applied,
            )
        iteration += 1
        tick_start = last_tick if last_tick is not None else 0
        record: dict[str, Any] = {
            "iteration": iteration,
            "checkpoint_id": f"cp{cp_index}",
            "mutation_id": last_mutation_id,
            "verdict": None,
            "gate": None,
            "window_ticks": window_ticks,
            "tick_start": tick_start,
            "tick_end": None,
            "events": [],
        }
        iterations.append(record)

        record["events"].append(
            emit(
                EVENT_TYPES["window_started"],
                {
                    "run_id": run_id,
                    "iteration": iteration,
                    "checkpoint_id": f"cp{cp_index}",
                    "window_ticks": window_ticks,
                    "speed": speed,
                    "start_tick": tick_start,
                    "start_day": checkpoint_record["day"],
                },
                game_tick=tick_start,
            )["event_id"]
        )

        res = bridge.set_speed(speed)
        if not res.get("ok"):
            record["verdict"] = "aborted"
            record["events"].append(_emit_iteration_completed(emit, run_id, record))
            return abort(
                "bridge_error", "retry.speed_failed",
                "game.speed failed", mutations_applied,
                details={"bridge_error": res.get("error")},
            )

        w_start = clock()
        window_budget = min(per_window_s, max(0.0, total_deadline - w_start))
        advanced = bridge.advance_window(
            window_ticks, budget_s=window_budget, clock=clock, sleep=sleep
        )
        if not advanced.get("ok"):
            record["verdict"] = "aborted"
            record["events"].append(_emit_iteration_completed(emit, run_id, record))
            berr = advanced.get("error") or {}
            reason = (
                "budget_per_window"
                if berr.get("code") == "retry.budget.per_window"
                else "bridge_error"
            )
            return abort(
                reason, berr.get("code", "retry.advance_failed"),
                berr.get("message", "window advance failed"), mutations_applied,
                details=berr.get("details"),
            )
        elapsed = clock() - w_start
        end_state = advanced["result"]
        tick_end = end_state.get("tick") if isinstance(end_state.get("tick"), int) else None
        record["tick_end"] = tick_end
        last_tick = tick_end

        if elapsed > per_window_s:
            record["verdict"] = "aborted"
            record["events"].append(_emit_iteration_completed(emit, run_id, record))
            return abort(
                "budget_per_window", "retry.budget.per_window",
                f"window {iteration} consumed {elapsed:.3f}s > budget {per_window_s}s",
                mutations_applied,
            )
        if clock() > total_deadline:
            record["verdict"] = "aborted"
            record["events"].append(_emit_iteration_completed(emit, run_id, record))
            return abort(
                "budget_total", "retry.budget.total",
                f"total budget {total_s}s exceeded in window {iteration}",
                mutations_applied,
            )

        try:
            verdict = evaluate(gate_def, end_state)
        except GateError as exc:
            record["verdict"] = "aborted"
            record["events"].append(_emit_iteration_completed(emit, run_id, record))
            return abort(
                "config_error", "retry.gate.invalid", str(exc), mutations_applied
            )
        record["gate"] = verdict
        record["events"].append(
            emit(
                EVENT_TYPES["gate_evaluated"],
                {
                    "run_id": run_id,
                    "iteration": iteration,
                    "gate_ref": gate_ref,
                    "passed": verdict["passed"],
                    "predicates": verdict["predicates"],
                    "early_exit": verdict["early_exit"],
                },
                game_tick=tick_end,
            )["event_id"]
        )

        record["verdict"] = "passed" if verdict["passed"] else "failed"
        record["events"].append(_emit_iteration_completed(emit, run_id, record))

        if verdict["passed"]:
            return finish("early_exit", "gate_passed", None, mutations_applied)

        # gate failed: retry while budget and mutation space remain
        if retries_used >= max_retries:
            return finish("exhausted", "max_retries", None, mutations_applied)
        popped = space.next()
        if popped is None:
            return finish("exhausted", "mutation_space_exhausted", None, mutations_applied)
        mut_index, mutation = popped
        retries_used += 1
        new_candidate, mut_error = MutationSpace.apply(candidate, mutation)
        if mut_error is None:
            candidate = new_candidate
            mutations_applied += 1
        raw_id = mutation.get("id") if isinstance(mutation, dict) else None
        last_mutation_id = raw_id if isinstance(raw_id, str) and raw_id else "<malformed>"
        raw_apply = mutation.get("apply") if isinstance(mutation, dict) else None
        mut_payload: dict[str, Any] = {
            "run_id": run_id,
            "iteration": iteration + 1,
            "mutation_id": last_mutation_id,
            "mutation_index": mut_index,
            "apply": raw_apply if isinstance(raw_apply, dict) else {},
            "applied": mut_error is None,
        }
        if mut_error is not None:
            mut_payload["error"] = {
                "code": mut_error["code"],
                "message": mut_error["message"],
            }
        emit(EVENT_TYPES["mutation_applied"], mut_payload, game_tick=tick_end)

        # reload the checkpoint and verify tick/day before the next window
        loaded = bridge.load(save_name)
        if not loaded.get("ok"):
            return abort(
                "bridge_error", "retry.checkpoint.load_failed",
                f"game.load {save_name!r} failed",
                mutations_applied, details={"bridge_error": loaded.get("error")},
            )
        restored = bridge.status()
        if not restored.get("ok"):
            return abort(
                "bridge_error", "retry.status.unavailable",
                "game.status failed after checkpoint reload",
                mutations_applied, details={"bridge_error": restored.get("error")},
            )
        r = restored["result"]
        if (
            r.get("tick") != checkpoint_record["tick"]
            or r.get("day") != checkpoint_record["day"]
        ):
            return abort(
                "reload_state_mismatch", "retry.reload.state_mismatch",
                f"reloaded state tick/day {r.get('tick')}/{r.get('day')} != "
                f"checkpoint {checkpoint_record['tick']}/{checkpoint_record['day']}",
                mutations_applied,
                details={
                    "expected": {
                        "tick": checkpoint_record["tick"],
                        "day": checkpoint_record["day"],
                    },
                    "observed": {"tick": r.get("tick"), "day": r.get("day")},
                },
            )
        last_tick = r.get("tick") if isinstance(r.get("tick"), int) else last_tick


def _emit_iteration_completed(emit, run_id: str, record: dict) -> str:
    envelope = emit(
        EVENT_TYPES["iteration_completed"],
        {
            "run_id": run_id,
            "iteration": record["iteration"],
            "checkpoint_id": record["checkpoint_id"],
            "verdict": record["verdict"],
            "gate_passed": bool(record["gate"] and record["gate"]["passed"]),
            "mutation_id": record["mutation_id"],
            "window_ticks": record["window_ticks"],
            "tick_start": record["tick_start"],
            "tick_end": record["tick_end"],
        },
        game_tick=record["tick_end"] if record["tick_end"] is not None else record["tick_start"],
    )
    return envelope["event_id"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _sim_bridge_from_config(config: dict) -> SimBridge:
    sim = config.get("sim") or {}
    effects = sim.get("effects") or []

    def on_advance(state: dict, ticks: int, call_index: int) -> None:
        for effect in effects:
            if int(effect.get("window", -1)) == call_index:
                for path, value in (effect.get("set") or {}).items():
                    _set_path(state, path, value)

    return SimBridge(
        state=sim.get("state") or {},
        on_advance=on_advance if effects else None,
        wall_per_window_s=float(sim.get("wall_per_window_s", 0.0)),
    )


def _set_path(node: dict, path: str, value: Any) -> None:
    segments = path.split(".")
    for segment in segments[:-1]:
        node = node.setdefault(segment, {})
    node[segments[-1]] = value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lab.retryloop",
        description="Checkpoint-reload retry loop (debug/eval mode; feature 003).",
    )
    parser.add_argument("--config", required=True, help="RetryConfig YAML path")
    parser.add_argument("--mode", choices=["sim", "live"], default="sim")
    parser.add_argument(
        "--bridge", default="http://127.0.0.1:8765", help="live bridge base URL"
    )
    parser.add_argument("--run-id", default=None, help="run.* run identifier")
    parser.add_argument("--episode-id", default=None, help="ep.* link (never fabricated)")
    parser.add_argument(
        "--scored-episode-active",
        action="store_true",
        help="simulate the scored-episode guard (must hard-reject)",
    )
    parser.add_argument(
        "--export", default=None, help="write a US5 fixture package to this dir"
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except RetryConfigError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2

    if args.mode == "sim":
        bridge = _sim_bridge_from_config(config)
    else:
        bridge = LiveBridge(args.bridge)

    result = run_loop(
        config,
        bridge,
        scored_episode_active=args.scored_episode_active,
        episode_id=args.episode_id,
        run_id=args.run_id,
    )

    if args.export:
        from lab.retryfixture import export_fixture

        fixture_dir = export_fixture(
            result,
            args.export,
            source="live-run" if args.mode == "live" else "synthesized",
        )
        result["fixture"] = str(fixture_dir)

    summary = {
        "ok": result["ok"],
        "outcome": result.get("outcome"),
        "reason": result.get("reason"),
        "run_id": result["run_id"],
        "iterations": len(result.get("iterations", [])),
        "events": len(result.get("events", [])),
        "error": result.get("error"),
    }
    if "fixture" in result:
        summary["fixture"] = result["fixture"]
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
