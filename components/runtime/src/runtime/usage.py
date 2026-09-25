"""Per-endpoint usage counters (feature 002; US5).

Thread-safe accumulator keyed by endpoint id: call counts plus provider-reported
prompt/completion tokens. A snapshot folds into ``episode_manifest(usage=...)``;
the tracker itself carries no secrets and no timestamps (those belong to the
episode envelope, not the manifest).
"""

from __future__ import annotations

import threading


class UsageTracker:
    """Lock-guarded per-endpoint counters; snapshot() is the only read."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[str, dict] = {}

    def record(self, endpoint_id: str, *,
               tokens: dict | None = None, cost: float | None = None) -> dict:
        with self._lock:
            e = self._counts.setdefault(endpoint_id, {
                "calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                "cost": 0.0})
            e["calls"] += 1
            if tokens:
                e["prompt_tokens"] += int(tokens.get("prompt_tokens") or 0)
                e["completion_tokens"] += int(tokens.get("completion_tokens") or 0)
            if cost is not None:
                e["cost"] += float(cost)
            return dict(e)

    def snapshot(self) -> dict[str, dict]:
        """Sorted deep-copy of all counters (deterministic for manifests)."""
        with self._lock:
            return {k: dict(v) for k, v in sorted(self._counts.items())}

    def reset(self) -> None:
        with self._lock:
            self._counts.clear()


DEFAULT_TRACKER = UsageTracker()
