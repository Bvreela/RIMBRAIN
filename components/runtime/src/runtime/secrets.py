"""Secret resolution for ``api_key_ref`` (feature 002; FR-002, SC-005).

Refs are ``env:NAME`` (os.environ at call time) or ``config:NAME`` (a key —
dotted path, top-level, or ``llm.NAME`` — in the gitignored
``upstream/rimagent/config.local.yaml``). Resolution happens only at call
time; resolved values are never serialized, logged, or returned in envelopes.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from .registry import REPO_ROOT, err

CONFIG_LOCAL = REPO_ROOT / "upstream" / "rimagent" / "config.local.yaml"


class SecretError(Exception):
    def __init__(self, envelope: dict):
        super().__init__(envelope["error"]["message"])
        self.envelope = envelope


def _config_lookup(name: str) -> str | None:
    """Dotted path, top-level, or `llm.` prefixed lookup in config.local.yaml."""
    if not CONFIG_LOCAL.is_file():
        return None
    doc = yaml.safe_load(CONFIG_LOCAL.read_text(encoding="utf-8")) or {}
    node = doc
    for part in name.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            node = None
            break
    if node is None:
        node = doc.get(name) or (doc.get("llm") or {}).get(name)
    return node if isinstance(node, str) else None


def resolve_api_key(api_key_ref: str | None) -> str | None:
    """Resolve a key ref to the secret string; ``None`` for open endpoints.

    Raises SecretError with the shared envelope on an unresolvable ref.
    """
    if api_key_ref is None:
        return None
    if api_key_ref.startswith("env:"):
        value = os.environ.get(api_key_ref[4:])
    elif api_key_ref.startswith("config:"):
        value = _config_lookup(api_key_ref[7:])
    else:
        raise SecretError(err(
            "secrets.ref.invalid",
            f"api_key_ref must be 'env:NAME' or 'config:NAME', got {api_key_ref!r}",
        ))
    if not value:
        raise SecretError(err(
            "secrets.ref.unresolved",
            f"api_key_ref {api_key_ref!r} did not resolve",
            {"ref_kind": api_key_ref.split(":", 1)[0]},
            retryable=True,
        ))
    return value
