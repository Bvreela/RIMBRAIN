"""Seeded-random property tests for contract primitives (CONTRACTS.md §9).

Covers: ID grammar fuzzing (valid and invalid shapes), schema/grammar parity,
and canonicalization stability (same input -> identical hash across runs,
key-order independence).

SEED is recorded here so a failure reproduces byte-for-byte: SEED = 0x52494D42
("RIMB" little-endian). Do not change it without recording the new value in
this comment.
"""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "components" / "contracts"
sys.path.insert(0, str(CONTRACTS_DIR / "src"))

from contracts import canonical_bytes, canonical_hash, canonical_text

SEED = 0x52494D42
SAMPLES = 500

ID_GRAMMAR = re.compile(r"^[a-z][a-z0-9]*\.[A-Za-z0-9][A-Za-z0-9_-]{2,63}$")
ID_SCHEMA = json.loads(
    (CONTRACTS_DIR / "schemas" / "common" / "id.schema.json").read_text(encoding="utf-8")
)
ID_VALIDATOR = jsonschema.Draft202012Validator(ID_SCHEMA)

REGISTERED_KINDS = [
    "evt", "ep", "obs", "plan", "goal", "task", "lock", "intent", "act",
    "ver", "req", "resp", "fix", "pack", "cmp", "blb", "pm",
]
KIND_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789"
IDENT_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"

# Golden canonicalization vector (language-independent, CONTRACTS.md §9):
# canonical_text(GOLDEN_OBJECT) must equal GOLDEN_TEXT on every platform.
GOLDEN_OBJECT = {
    "k": [1, 2.5, "x\n", True, None],
    "a": {"z": False, "b": None},
    "num": 0.001,
    "big": 1e21,
}
GOLDEN_TEXT = (
    '{"a":{"b":null,"z":false},"big":1e+21,'
    '"k":[1,2.5,"x\\n",true,null],"num":0.001}'
)
GOLDEN_HASH = "d36744ca2164c5d81c3828dea77795b096b1c75b632f7a68b2770cc7b37a0ed9"  # sha256 of GOLDEN_TEXT (utf-8)


def _rng() -> random.Random:
    return random.Random(SEED)


def _random_valid_id(rng: random.Random) -> str:
    kind = rng.choice(REGISTERED_KINDS) + "".join(
        rng.choice(KIND_CHARS) for _ in range(rng.randrange(0, 4))
    )
    ident_len = rng.randrange(3, 65)
    ident = rng.choice(IDENT_CHARS.replace("-", "").replace("_", "")) + "".join(
        rng.choice(IDENT_CHARS) for _ in range(ident_len - 1)
    )
    return f"{kind}.{ident}"


def _random_invalid_id(rng: random.Random) -> str:
    """Produce a string that violates the ID grammar."""
    shape = rng.randrange(8)
    if shape == 0:  # uppercase / bad kind start
        return f"{rng.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ_-0123456789')}vt.a1b"
    if shape == 1:  # no separator
        return "evt" + rng.choice(["", "abc", "-x.y"])
    if shape == 2:  # identifier too short (<3 chars after kind)
        return f"evt.{''.join(rng.choice(IDENT_CHARS) for _ in range(rng.randrange(0, 3)))}"
    if shape == 3:  # identifier too long (>64 chars)
        return "evt." + "a" * rng.randrange(65, 200)
    if shape == 4:  # illegal characters
        bad = rng.choice([" ", "!", ":", "/", ".", "@", "é"])
        pos = rng.randrange(0, 5)
        return "evt.a1b"[:pos] + bad + "evt.a1b"[pos:]
    if shape == 5:  # empty / whitespace / non-string-ish
        return rng.choice(["", " ", ".", "evt.", ".abc", "evt..abc"])
    if shape == 6:  # identifier starting with - or _ (first char must be alnum)
        return f"evt.{rng.choice('-_')}{''.join(rng.choice(IDENT_CHARS) for _ in range(3))}"
    # kind containing uppercase or separator characters
    return f"ev{rng.choice(['T', '-', '_'])}.a1b"


def _random_json_value(rng: random.Random, depth: int = 0) -> object:
    choice = rng.randrange(7 if depth < 4 else 5)
    if choice == 0:
        return None
    if choice == 1:
        return rng.choice([True, False])
    if choice == 2:
        return rng.randrange(-(10 ** rng.randrange(1, 10)), 10 ** rng.randrange(1, 10))
    if choice == 3:
        return rng.choice([0.0, -0.0, 1e-7, 1e21, 3.14159, rng.random() * 10 ** rng.randrange(-8, 8)])
    if choice == 4:
        return "".join(rng.choice("abcXYZ019 _-\t\n\"\\€") for _ in range(rng.randrange(0, 20)))
    if choice == 5:
        return [_random_json_value(rng, depth + 1) for _ in range(rng.randrange(0, 6))]
    return {
        f"k{rng.randrange(0, 100)}": _random_json_value(rng, depth + 1)
        for _ in range(rng.randrange(0, 6))
    }


def test_valid_id_fuzz() -> None:
    rng = _rng()
    for _ in range(SAMPLES):
        value = _random_valid_id(rng)
        assert ID_GRAMMAR.fullmatch(value), value
        assert ID_VALIDATOR.is_valid(value), value


def test_invalid_id_fuzz() -> None:
    rng = _rng()
    rejected = 0
    for _ in range(SAMPLES):
        value = _random_invalid_id(rng)
        if ID_GRAMMAR.fullmatch(value):
            continue  # generator occasionally emits a valid string; skip those
        rejected += 1
        assert not ID_VALIDATOR.is_valid(value), value
    assert rejected > SAMPLES // 2, "invalid generator mostly produced valid ids"


def test_schema_grammar_parity() -> None:
    """The schema's pattern and the reference grammar must agree on every sample."""
    rng = _rng()
    for _ in range(SAMPLES):
        for value in (_random_valid_id(rng), _random_invalid_id(rng)):
            assert bool(ID_GRAMMAR.fullmatch(value)) == ID_VALIDATOR.is_valid(value), value


def test_canonical_golden_vector() -> None:
    assert canonical_text(GOLDEN_OBJECT) == GOLDEN_TEXT
    assert canonical_hash(GOLDEN_OBJECT) == GOLDEN_HASH


def test_canonical_determinism_same_input() -> None:
    rng = _rng()
    for _ in range(SAMPLES):
        value = _random_json_value(rng)
        assert canonical_bytes(value) == canonical_bytes(value)
        assert canonical_hash(value) == canonical_hash(
            json.loads(canonical_bytes(value).decode("utf-8"))
        )


def test_canonical_key_order_independence() -> None:
    rng = _rng()
    for _ in range(SAMPLES):
        items = [(f"key{i}", _random_json_value(rng, depth=3)) for i in range(rng.randrange(1, 8))]
        forward = dict(items)
        shuffled = dict(rng.sample(items, len(items)))
        assert canonical_bytes(forward) == canonical_bytes(shuffled)


def test_canonical_rejects_non_finite() -> None:
    import math
    import pytest

    for bad in (math.nan, math.inf, -math.inf, {"x": math.nan}):
        with pytest.raises(Exception):
            canonical_bytes(bad)
