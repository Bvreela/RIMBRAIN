"""Canonical JSON serialization per RFC 8785 (JSON Canonicalization Scheme).

Deterministic byte encoding used for corpus hashes, fixture manifests, and
record identity across RimBrainAgent components:

- object keys sorted by UTF-16 code units (RFC 8785 §3.2.3);
- strings emitted with the minimal JSON.stringify escape set (only ``"``,
  ``\\``, and control characters < U+0020 are escaped; everything else is
  raw UTF-8);
- numbers emitted per ECMAScript ``Number::toString`` shortest round-trip
  rules; non-finite values (NaN, Infinity) are rejected;
- no whitespace; output is UTF-8.

Language-independent golden vectors for this encoder live in
``tests/contract/test_primitives_property.py``.
"""

from __future__ import annotations

import hashlib
import math
import re

__all__ = ["canonical_bytes", "canonical_text", "canonical_hash", "CanonicalJSONError"]


class CanonicalJSONError(ValueError):
    """Raised when a value cannot be represented in canonical JSON."""


_STRING_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}

_REPR_PARTS = re.compile(r"(?P<sign>-?)(?P<int>\d+)(?:\.(?P<frac>\d+))?(?:[eE](?P<exp>[+-]?\d+))?$")


def _encode_string(value: str) -> str:
    out = ['"']
    for ch in value:
        escape = _STRING_ESCAPES.get(ch)
        if escape is not None:
            out.append(escape)
        elif ord(ch) < 0x20:
            out.append("\\u%04x" % ord(ch))
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _encode_number(value: int | float) -> str:
    """Serialize a number the way ECMAScript Number::toString does (RFC 8785 §3.2.2.3)."""
    if isinstance(value, bool):
        raise CanonicalJSONError("booleans are not numbers")
    if isinstance(value, int):
        return str(value)
    if not math.isfinite(value):
        raise CanonicalJSONError("non-finite numbers (NaN/Infinity) are not valid canonical JSON")
    if value == 0:
        return "0"  # JSON.stringify(-0) === "0"

    # repr() yields the shortest decimal string that round-trips, which is the
    # same digit sequence ECMAScript's shortest-form algorithm produces.
    match = _REPR_PARTS.fullmatch(repr(value))
    if match is None:  # pragma: no cover - defensive; repr() always matches
        raise CanonicalJSONError(f"cannot canonicalize float {value!r}")
    sign = match.group("sign")
    frac = match.group("frac") or ""
    # value = int(raw_digits) * 10^exponent; strip leading zeros (no value
    # change), then trailing zeros (each removed zero raises exponent by 1).
    raw_digits = (match.group("int") + frac).lstrip("0")
    exponent = int(match.group("exp") or 0) - len(frac)
    digits = raw_digits.rstrip("0")
    exponent += len(raw_digits) - len(digits)
    # ECMAScript normalization: value = s * 10^(n - k), k = len(s), s = digits.
    k = len(digits)
    n = exponent + k

    if k <= n <= 21:
        body = digits + "0" * (n - k)
    elif 0 < n <= 21:
        body = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * (-n) + digits
    else:
        body = digits if k == 1 else digits[0] + "." + digits[1:]
        body += "e" + ("+" if n - 1 >= 0 else "-") + str(abs(n - 1))
    return sign + body


def _key_sort_bytes(key: str) -> bytes:
    # RFC 8785 sorts keys by UTF-16 code units; UTF-16-BE bytes give that order.
    return key.encode("utf-16-be", errors="surrogatepass")


def _encode(value: object) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _encode_string(value)
    if isinstance(value, (int, float)):
        return _encode_number(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_encode(item) for item in value) + "]"
    if isinstance(value, dict):
        parts = []
        for key in sorted(value.keys(), key=_key_sort_bytes):
            if not isinstance(key, str):
                raise CanonicalJSONError(f"object keys must be strings, got {type(key).__name__}")
            parts.append(_encode_string(key) + ":" + _encode(value[key]))
        return "{" + ",".join(parts) + "}"
    raise CanonicalJSONError(f"unsupported type for canonical JSON: {type(value).__name__}")


def canonical_text(obj: object) -> str:
    """Return the canonical JSON serialization of ``obj`` as text."""
    return _encode(obj)


def canonical_bytes(obj: object) -> bytes:
    """Return the canonical JSON serialization of ``obj`` as UTF-8 bytes."""
    return _encode(obj).encode("utf-8")


def canonical_hash(obj: object) -> str:
    """Return the lowercase hex SHA-256 of ``canonical_bytes(obj)``."""
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()
