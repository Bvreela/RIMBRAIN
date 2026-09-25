"""Pack-side contract tests (feature 019,
contracts/combat-capability.md): the `combat:` cfg block validates
against the schema, an invalid cfg is rejected, and the cfg/script
shape-gate keeps the dev harness separate from the fair surface.
"""

import json
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
for _p in ("components/runtime/src", "components/contracts/src"):
    if str(REPO / _p) not in sys.path:
        sys.path.insert(0, str(REPO / _p))

from runtime import templates  # noqa: E402

SCHEMA = json.loads((REPO / "components" / "contracts" / "schemas" /
                     "runtime" / "pack.schema.json").read_text())
PACK = (REPO / "components" / "rimbrain" / "packs" /
        "combat-defense-v0" / "pack.yaml")
DEVLAB = (REPO / "components" / "rimbrain" / "packs" /
          "dev-lab-v0" / "pack.yaml")


def _doc(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_combat_pack_schema_valid():
    jsonschema.validate(_doc(PACK), SCHEMA)


def test_combat_cfg_rejects_wrong_types():
    doc = _doc(PACK)
    doc["combat"]["delegate_order"] = 5
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, SCHEMA)
    doc = _doc(PACK)
    doc["combat"]["engage_radius"] = -1
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, SCHEMA)


def test_delegate_order_nullable_for_pack_owned_path():
    doc = _doc(PACK)
    doc["combat"]["delegate_order"] = None
    jsonschema.validate(doc, SCHEMA)


def test_fair_pack_has_no_dev_methods():
    doc = _doc(PACK)
    methods = {t.get("method") for t in
               (doc.get("capabilities") or {}).get("templates") or []}
    assert not any(str(m).startswith("dev.") for m in methods)
    assert doc.get("class") == "fair"


def test_cfg_block_is_not_a_harness_phase():
    """A fair `combat:` cfg block must not compile into a kind:combat
    phase — the scripted harness keeps its own shape."""
    phases = templates.phases_of(_doc(PACK))
    assert not any(p.get("kind") == "combat" for p in phases)
    # and the dev harness still gets its combat phase
    phases = templates.phases_of(_doc(DEVLAB))
    assert any(p.get("kind") == "combat" for p in phases)


def test_devlab_dev_combat_cfg_surface():
    doc = _doc(DEVLAB)
    assert doc.get("dev_combat", {}).get("allow_unarmed") is True
    # scripted combat block untouched
    assert doc["combat"].get("checkpoint")
