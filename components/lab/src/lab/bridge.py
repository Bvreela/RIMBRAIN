"""GameCtl bridge abstraction for checkpoint-retry loops (feature 003, T048).

Transport-agnostic control surface consumed by ``lab.retryloop``:

- ``save(name)`` / ``load(name)`` / ``list_saves()`` -- checkpoint snapshot and
  restore (FR-201, FR-206);
- ``status()`` -- observed state dict ``{state, tick, day, ...}`` used for gate
  evaluation and reload verification (FR-210);
- ``set_speed(speed)`` -- game speed 0..4 applied while a window advances;
- ``advance_window(ticks, budget_s, clock, sleep)`` -- advance ``ticks`` game
  ticks bounded by a wall-clock budget (FR-207).

Every method returns the shared result envelope ``{ok: true, result: ...}`` /
``{ok: false, error: {code, message, retryable, details?}}`` -- transport and
game errors are structured, never raised raw (FR-006).

Implementations:

- ``LiveBridge`` -- HTTP RPC against the zorrobyte RimBridge surface
  (``POST <base>/rpc {method, params} -> {ok, result}``,
  ``GET <base>/events?since=N``).
- ``SimBridge`` -- in-memory deterministic fake for offline tests: saves are
  snapshot state dicts, ``advance_window`` bumps tick/day deterministically and
  can consume wall-clock from an injected ``ManualClock``.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from copy import deepcopy
from typing import Any, Callable

__all__ = [
    "DEFAULT_BRIDGE_URL",
    "TICKS_PER_DAY",
    "GameCtl",
    "LiveBridge",
    "SimBridge",
    "ManualClock",
    "error_envelope",
]

DEFAULT_BRIDGE_URL = "http://127.0.0.1:8765"
TICKS_PER_DAY = 60000  # RimWorld: 60,000 ticks per game-day


def error_envelope(
    code: str,
    message: str,
    retryable: bool = False,
    details: dict | None = None,
) -> dict:
    """Shared failure grammar (common/error.schema.json)."""
    error: dict[str, Any] = {"code": code, "message": message, "retryable": retryable}
    if details is not None:
        error["details"] = details
    return {"ok": False, "error": error}


class ManualClock:
    """Deterministic monotonic clock for offline runs/tests.

    ``clock()`` returns the current virtual time in seconds; ``advance(s)``
    moves it forward. SimBridge consumes it via ``wall_per_window_s`` so budget
    bounds (FR-207) are exercised deterministically, and emitted event
    ``wall_time_utc`` values are reproducible.
    """

    def __init__(self, start: float = 0.0) -> None:
        self.t = float(start)

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += float(seconds)


class GameCtl:
    """Interface every game-control bridge implements.

    Methods return ``{ok, result|error}`` envelopes; ``advance_window`` is lab
    loop control (not a bridge RPC): it advances ``ticks`` game ticks, honoring
    a wall-clock budget via the injected ``clock``/``sleep``.
    """

    def save(self, name: str) -> dict:  # pragma: no cover - interface
        raise NotImplementedError

    def load(self, name: str) -> dict:  # pragma: no cover - interface
        raise NotImplementedError

    def status(self) -> dict:  # pragma: no cover - interface
        raise NotImplementedError

    def set_speed(self, speed: int) -> dict:  # pragma: no cover - interface
        raise NotImplementedError

    def pause(self) -> dict:  # pragma: no cover - interface
        raise NotImplementedError

    def list_saves(self) -> dict:  # pragma: no cover - interface
        raise NotImplementedError

    def advance_window(
        self,
        ticks: int,
        budget_s: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> dict:  # pragma: no cover - interface
        raise NotImplementedError


class LiveBridge(GameCtl):
    """HTTP transport over the zorrobyte bridge surface.

    ``POST <base>/rpc {"method": ..., "params": {...}}`` -> ``{ok, result}``;
    ``GET <base>/events?since=N`` -> ``{events, last_seq, head_seq, assisted}``.
    Transport failures (connectivity, HTTP status, non-JSON bodies) return
    ``{ok: false, error: {code: "bridge.transport.*", retryable: true}}``.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BRIDGE_URL,
        timeout_s: float = 10.0,
        poll_interval_s: float = 0.25,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = float(timeout_s)
        self.poll_interval_s = float(poll_interval_s)

    # -- transport ----------------------------------------------------------

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        body = json.dumps({"method": method, "params": params or {}}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/rpc",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            return error_envelope(
                "bridge.transport.http",
                f"{method}: HTTP {exc.code} from {self.base_url}",
                retryable=True,
                details={"method": method, "status": exc.code},
            )
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            return error_envelope(
                "bridge.transport.unreachable",
                f"{method}: cannot reach {self.base_url}: {exc}",
                retryable=True,
                details={"method": method},
            )
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return error_envelope(
                "bridge.transport.bad_response",
                f"{method}: non-JSON response: {exc}",
                retryable=True,
                details={"method": method},
            )
        if isinstance(parsed, dict) and "ok" in parsed:
            return parsed
        return {"ok": True, "result": parsed}

    def events(self, since: int = 0) -> dict:
        """``GET /events?since=N`` -> ``{events, last_seq, head_seq, assisted}``."""
        try:
            with urllib.request.urlopen(
                f"{self.base_url}/events?since={int(since)}", timeout=self.timeout_s
            ) as resp:
                parsed = json.loads(resp.read())
        except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
            return error_envelope(
                "bridge.transport.unreachable",
                f"events: cannot reach {self.base_url}: {exc}",
                retryable=True,
            )
        return {"ok": True, "result": parsed}

    # -- GameCtl ------------------------------------------------------------

    def save(self, name: str) -> dict:
        return self._rpc("game.save", {"name": name})

    def load(self, name: str) -> dict:
        return self._rpc("game.load", {"name": name})

    def status(self) -> dict:
        return self._rpc("game.status", {})

    def set_speed(self, speed: int) -> dict:
        return self._rpc("game.speed", {"speed": int(speed)})

    def pause(self) -> dict:
        return self._rpc("game.pause", {})

    def list_saves(self) -> dict:
        return self._rpc("game.list_saves", {})

    def advance_window(
        self,
        ticks: int,
        budget_s: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> dict:
        """Poll ``game.status`` until the game has advanced ``ticks`` ticks.

        ``budget_s`` is a wall-clock cap measured on the injected ``clock``;
        exceeding it returns ``{ok:false, code:"retry.budget.per_window"}``.
        """
        start = self.status()
        if not start.get("ok"):
            return start
        start_tick = start["result"].get("tick")
        if not isinstance(start_tick, int):
            return error_envelope(
                "bridge.status.no_tick",
                "game.status did not report an integer tick",
                retryable=True,
            )
        deadline = None if budget_s is None else clock() + float(budget_s)
        while True:
            if deadline is not None and clock() > deadline:
                return error_envelope(
                    "retry.budget.per_window",
                    f"window of {ticks} ticks exceeded wall-clock budget "
                    f"{budget_s}s (start tick {start_tick})",
                    details={"ticks": ticks, "budget_s": budget_s},
                )
            sleep(self.poll_interval_s)
            cur = self.status()
            if not cur.get("ok"):
                return cur
            state = cur["result"]
            if state.get("state") not in ("playing",):
                return error_envelope(
                    "bridge.game.not_playing",
                    f"game left 'playing' state mid-window: {state.get('state')!r}",
                    details={"state": state.get("state")},
                )
            tick = state.get("tick")
            if isinstance(tick, int) and tick >= start_tick + ticks:
                return {"ok": True, "result": state}


class SimBridge(GameCtl):
    """In-memory deterministic fake for offline tests and ``--mode sim``.

    - ``state`` is a plain dict; ``tick``/``day``/``speed``/``state`` keys are
      managed, everything else is free-form gate-observable state.
    - ``save`` snapshots a deep copy; ``load`` restores it (checkpoint reload
      returns the game to the checkpoint tick/day exactly -- FR-210).
    - ``advance_window`` bumps ``tick`` by ``ticks`` and derives ``day``;
      ``on_advance(state, ticks, call_index)`` may mutate state each window so
      gates can observe scripted progress.
    - ``on_load(state, name)`` runs after a restore -- tests use it to simulate
      state corruption on reload.
    - ``wall_per_window_s`` is charged to a ``ManualClock`` passed via the
      ``clock`` argument (or the constructor), making budget tests
      deterministic; with a real clock it is ignored.
    """

    def __init__(
        self,
        state: dict | None = None,
        on_advance: Callable[[dict, int, int], None] | None = None,
        on_load: Callable[[dict, str], None] | None = None,
        wall_per_window_s: float = 0.0,
        clock: ManualClock | None = None,
    ) -> None:
        self._state: dict = deepcopy(state) if state else {}
        self._state.setdefault("state", "playing")
        self._state.setdefault("tick", 0)
        self._state.setdefault("day", self._state["tick"] // TICKS_PER_DAY)
        self._state.setdefault("speed", 0)
        self._saves: dict[str, dict] = {}
        self._modified_counter = 0
        self._advance_calls = 0
        self._on_advance = on_advance
        self._on_load = on_load
        self._wall_per_window_s = float(wall_per_window_s)
        self._clock = clock

    # -- introspection helpers for tests ------------------------------------

    @property
    def saves(self) -> dict[str, dict]:
        return self._saves

    @property
    def advance_calls(self) -> int:
        return self._advance_calls

    @property
    def current_state(self) -> dict:
        return deepcopy(self._state)

    # -- GameCtl ------------------------------------------------------------

    def save(self, name: str) -> dict:
        if not isinstance(name, str) or not name:
            return error_envelope("sim.save.invalid_name", "save name must be non-empty")
        self._modified_counter += 1
        self._saves[name] = {
            "state": deepcopy(self._state),
            "modified": self._modified_counter,
        }
        return {"ok": True, "result": {"name": name}}

    def load(self, name: str) -> dict:
        entry = self._saves.get(name)
        if entry is None:
            return error_envelope(
                "sim.save.not_found", f"no save named {name!r}", details={"name": name}
            )
        self._state = deepcopy(entry["state"])
        if self._on_load is not None:
            self._on_load(self._state, name)
        return {"ok": True, "result": {"name": name}}

    def status(self) -> dict:
        return {"ok": True, "result": deepcopy(self._state)}

    def set_speed(self, speed: int) -> dict:
        if not isinstance(speed, int) or isinstance(speed, bool) or not 0 <= speed <= 4:
            return error_envelope(
                "sim.speed.invalid", f"speed {speed!r} is not an integer in 0..4"
            )
        self._state["speed"] = speed
        return {"ok": True, "result": {"speed": speed}}

    def pause(self) -> dict:
        self._state["paused"] = True
        return {"ok": True, "result": {"paused": True}}

    def list_saves(self) -> dict:
        entries = [
            {"name": name, "modified": entry["modified"]}
            for name, entry in sorted(self._saves.items())
        ]
        return {"ok": True, "result": entries}

    def advance_window(
        self,
        ticks: int,
        budget_s: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> dict:
        if not isinstance(ticks, int) or isinstance(ticks, bool) or ticks < 1:
            return error_envelope(
                "sim.advance.invalid", f"window ticks {ticks!r} is not an integer >= 1"
            )
        self._advance_calls += 1
        self._state["tick"] += ticks
        self._state["day"] = self._state["tick"] // TICKS_PER_DAY
        if self._on_advance is not None:
            self._on_advance(self._state, ticks, self._advance_calls)
        # Charge virtual wall-clock when the injected clock supports it
        # (ManualClock); a real monotonic clock simply does not advance.
        target = clock if hasattr(clock, "advance") else self._clock
        if target is not None and self._wall_per_window_s:
            target.advance(self._wall_per_window_s)  # type: ignore[union-attr]
        return {"ok": True, "result": deepcopy(self._state)}
