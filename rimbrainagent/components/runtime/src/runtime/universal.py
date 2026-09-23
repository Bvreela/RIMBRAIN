"""Universal rules entry point (feature 011/012; FR-901/909, UR-BRN-011).

All rule content lives in the pack's ``universal.rules[]`` — this module
only builds the evaluation context and delegates to ``policy.run_rules``.
Modes call ``apply_rules`` once per poll, after reflexes. Every write goes
through the single dispatcher; every rule is fail-closed.
"""

from __future__ import annotations

from . import policy


def apply_rules(dispatcher, game, obs, pack: dict, state: dict, *,
                tick: int = 0, poll: int | None = None,
                vars: dict | None = None,
                decisions: list | None = None) -> list[dict]:
    """Run the pack's universal rules for this poll. Returns the fired
    dispatches (rule id, template, ok, params) for evidence."""
    rules = ((pack or {}).get("universal") or {}).get("rules") or []
    ctx = policy.Ctx(cfg=pack, obs=obs, game=game, state=state,
                     persist=dict(vars or {}), tick=tick, poll=poll,
                     decisions=decisions)
    return policy.run_rules(rules, dispatcher, ctx, source="rule")
