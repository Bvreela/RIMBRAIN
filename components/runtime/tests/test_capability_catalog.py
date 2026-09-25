"""Capability-catalog consistency tests (feature 014; FR-1201..1205,
SC-1201..1205)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "components" / "runtime" / "src"))
sys.path.insert(0, str(REPO_ROOT / "components" / "contracts" / "src"))

from runtime import policy, templates  # noqa: E402

CATALOG = REPO_ROOT / "components" / "rimbrain" / "capability-catalog.yaml"
SCHEMA = (REPO_ROOT / "components" / "contracts" / "schemas" / "rimbrain"
          / "capability-catalog.schema.json")
FORBIDDEN_POLICY_KEYS = {"when", "try", "effect", "priority", "threshold",
                         "phases", "rules", "exit", "while", "needs",
                         "cooldown", "for_each", "op", "value"}


@pytest.fixture(scope="module")
def catalog():
    return yaml.safe_load(CATALOG.read_text(encoding="utf-8"))


def _registry_ids() -> dict[str, set[str]]:
    # templates span the pack family: the fair pack (play surface) plus
    # the dev-class harness (spawn/heal tooling it legitimately owns)
    tpl_ids: set[str] = set()
    for pid in ("start-mode-v0", "dev-lab-v0", "combat-defense-v0"):
        pk = templates.load_pack(pid)["pack"]
        tpls = pk.get("templates") or \
            (pk.get("capabilities") or {}).get("templates") or []
        tpl_ids |= {t["id"] for t in tpls}
    return {
        "template": tpl_ids,
        "fn": set(policy.FN.keys()),
        "selector": set(policy._SELECTORS.keys()),
    }


def test_catalog_validates_against_schema(catalog):
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(catalog)


def test_implemented_entries_resolve(catalog):
    """FR-1204: every implemented entry maps to a real registry member."""
    reg = _registry_ids()
    for e in catalog["entries"]:
        if e["status"] != "implemented" or e["kind"] == "capability":
            continue  # runtime-internal bridge capabilities
        assert e["id"] in reg.get(e["kind"], set()), \
            f"implemented {e['kind']} '{e['id']}' not in registry"


def test_registry_members_catalogued(catalog):
    """FR-1204: every public registry member appears in the catalog."""
    cat_ids = {e["id"] for e in catalog["entries"]}
    reg = _registry_ids()
    for kind, ids in reg.items():
        for rid in ids:
            assert rid in cat_ids, f"registry {kind} '{rid}' uncatalogued"


def test_no_policy_fields(catalog):
    """SC-1205/UR-BRN-017: catalog carries capability data, never policy."""
    for e in catalog["entries"]:
        bad = FORBIDDEN_POLICY_KEYS & set(e)
        assert not bad, f"entry {e['id']} holds policy keys: {bad}"


def test_baseline_surface_fully_mapped(catalog):
    """SC-1201: every baseline RPC method is covered by some entry."""
    inv = json.loads((REPO_ROOT / "baselines" / "upstream-85cb050"
                      / "rpc-inventory.json").read_text())
    mapped = {m for e in catalog["entries"]
              for m in (e.get("bridge_methods") or [])}
    unmapped = [i["name"] for i in inv if i["name"] not in mapped]
    assert unmapped == [], f"unmapped bridge surface: {unmapped}"


def test_audit_tool_smoke(catalog):
    """SC-1201: baseline audit exits 0 once catalog is seeded."""
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import capability_audit  # noqa: E402
    assert capability_audit.main([]) == 0
