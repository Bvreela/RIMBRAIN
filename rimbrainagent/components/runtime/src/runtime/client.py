"""Call adapters (feature 002; FR-006/FR-011).

Two wire shapes keyed on ``endpoint.api``:

- ``openai-compat`` — POST ``{base_url}/chat/completions`` and
  ``/embeddings``. ``strict: true`` endpoints receive no provider extension
  fields (``extra_body``/``chat_template_kwargs``/``reasoning``) — the
  verified Gemini 400 failure (FR-011).
- ``systemone`` — POST ``{state, questions}`` to ``decide_path`` → typed
  answers (local Laya ``/v1/systemone``, hosted ``/api/alpha/decisions``).

Every failure returns the shared envelope; secrets resolve at call time only.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .registry import err, get_endpoint
from .secrets import SecretError, resolve_api_key
from .usage import DEFAULT_TRACKER, UsageTracker

_TIMEOUT_S = 60
_PROVIDER_EXTENSIONS = ("extra_body", "chat_template_kwargs")


def _record_usage(tracker: UsageTracker | None, ep: dict, body: dict) -> None:
    """Fold provider-reported usage into the tracker when one is supplied."""
    if tracker is not None and isinstance(body, dict):
        tracker.record(ep["id"], tokens=body.get("usage") or None)


def _post_json(url: str, payload: dict, key: str | None,
               timeout: int = _TIMEOUT_S) -> dict:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"ok": True, "body": json.loads(resp.read() or b"null")}
    except urllib.error.HTTPError as exc:
        return err("client.http",
                   f"HTTP {exc.code} from {url}",
                   {"status": exc.code, "url": url},
                   retryable=exc.code >= 500 or exc.code == 429)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return err("client.unreachable", str(getattr(exc, "reason", exc)),
                   {"url": url}, retryable=True)


def _key_for(ep: dict) -> str | None:
    try:
        return resolve_api_key(ep.get("api_key_ref"))
    except SecretError as exc:
        raise exc


def openai_compat_chat(endpoint_id_or_entry, model: str, messages: list,
                       tools: list | None = None,
                       extra_body: dict | None = None,
                       timeout: int = _TIMEOUT_S,
                       usage_tracker: UsageTracker | None = None) -> dict:
    """OpenAI-compatible chat call; strips provider extensions when strict."""
    ep = (get_endpoint(endpoint_id_or_entry)
          if isinstance(endpoint_id_or_entry, str) else endpoint_id_or_entry)
    if ep is None:
        return err("registry.endpoint.missing", "unknown endpoint",
                   {"endpoint": endpoint_id_or_entry})
    if ep["api"] != "openai-compat":
        return err("client.api_mismatch",
                   f"endpoint '{ep['id']}' is api={ep['api']}, not openai-compat")
    payload = {"model": model, "messages": messages}
    if tools:
        payload["tools"] = tools
    if extra_body and not ep.get("strict"):
        payload.update(extra_body)
    elif extra_body:
        stripped = [k for k in extra_body if k in _PROVIDER_EXTENSIONS or True]
        payload.setdefault("_meta", {})["stripped"] = stripped
    try:
        key = _key_for(ep)
    except SecretError as exc:
        return exc.envelope
    r = _post_json(ep["base_url"].rstrip("/") + "/chat/completions",
                   payload, key, timeout)
    if r["ok"]:
        _record_usage(usage_tracker, ep, r["body"])
    return r if not r["ok"] else {"ok": True, "body": r["body"]}


def openai_compat_embed(endpoint_id_or_entry, model: str, inputs: list,
                        timeout: int = _TIMEOUT_S,
                        usage_tracker: UsageTracker | None = None) -> dict:
    ep = (get_endpoint(endpoint_id_or_entry)
          if isinstance(endpoint_id_or_entry, str) else endpoint_id_or_entry)
    if ep is None:
        return err("registry.endpoint.missing", "unknown endpoint",
                   {"endpoint": endpoint_id_or_entry})
    try:
        key = _key_for(ep)
    except SecretError as exc:
        return exc.envelope
    r = _post_json(ep["base_url"].rstrip("/") + "/embeddings",
                   {"model": model, "input": inputs}, key, timeout)
    if r["ok"]:
        _record_usage(usage_tracker, ep, r["body"])
    return r


def systemone_decide(endpoint_id_or_entry, state: str, questions: dict,
                     model: str | None = None,
                     timeout: int = _TIMEOUT_S,
                     usage_tracker: UsageTracker | None = None) -> dict:
    """Typed-decision call: POST {state, questions[, model]} to decide_path.

    ``model`` is included only when provided — hosted decisions requires it;
    local Laya routes a single loaded family and 422s on unknown names.
    """
    ep = (get_endpoint(endpoint_id_or_entry)
          if isinstance(endpoint_id_or_entry, str) else endpoint_id_or_entry)
    if ep is None:
        return err("registry.endpoint.missing", "unknown endpoint",
                   {"endpoint": endpoint_id_or_entry})
    if ep["api"] != "systemone":
        return err("client.api_mismatch",
                   f"endpoint '{ep['id']}' is api={ep['api']}, not systemone")
    try:
        key = _key_for(ep)
    except SecretError as exc:
        return exc.envelope
    url = ep["base_url"].rstrip("/") + ep["decide_path"]
    payload = {"state": state, "questions": questions}
    if model:
        payload["model"] = model
    r = _post_json(url, payload, key, timeout)
    if r["ok"]:
        _record_usage(usage_tracker, ep, r["body"])
    return r
