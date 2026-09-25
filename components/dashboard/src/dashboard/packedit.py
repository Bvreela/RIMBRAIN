"""Guided pack editor document model (feature 018; FR-014..019, FR-024).

Pure logic over a ``yaml.safe_load``'d pack doc: outline tree keyed to
the on-disk layout (v0 paths get unified-vocabulary labels; v1 sections
show when present), path get/set helpers for form writes, and the
save-as-new write path (new sibling pack, ``derived_from`` lineage —
the source file is never touched).

Tk glue lives in overlay.py; ``api.validate_pack_doc`` (facade) runs
the loader-identical checks before any write.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

# slug must keep `pack.<name>` inside the schema's pack_id grammar, so
# the first char is [a-z0-9] (the contract's [a-z0-9-]+ minus the
# leading-dash case the pack_id pattern would reject)
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

_META_KEYS = ("schema_version", "pack_id", "revision", "policy_version",
              "class", "derived_from", "meta")
_HIDDEN = {"jobs", "decision_map"}  # dead v0 fields (dropped in v1)
_CFG_KEYS = ("decide", "mutate", "fastevolve", "vitals", "blueprints",
             "defense", "improve", "cycle", "combat", "metrics",
             "action_list", "fallback_plan")


def load_doc(path: Path) -> dict:
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else {}


def source_id(path: Path, packs_dir: Path | None = None) -> str:
    """Pack id for a file: folder pack -> parent dir; flat -> stem."""
    p = Path(path)
    return p.parent.name if p.name == "pack.yaml" else p.stem


def get_path(doc: dict, dotted: str):
    node = doc
    for part in dotted.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def set_path(doc: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    node = doc
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _node(nid: str, label: str, path: str | None,
          children: list | None = None) -> dict:
    return {"id": nid, "label": label, "path": path,
            "children": children or []}


def build_outline(doc: dict) -> list[dict]:
    """v0-path -> unified-vocabulary label map (contracts/
    pack-edit-save.md). v1 sections appear only when the doc carries
    them; when both exist the v1 node wins and the retained v0 cfg
    blocks still show under Senses (they're the @cfg: alias map)."""
    out = [_node("meta", "Meta", None)]
    v1 = int(doc.get("schema_version") or 0) >= 1

    if (doc.get("capabilities") or {}).get("templates") is not None:
        out.append(_node("caps", "Capabilities", "capabilities.templates"))
    elif doc.get("templates") is not None:
        out.append(_node("caps", "Capabilities", "templates"))
    if doc.get("reflexes") is not None:
        out.append(_node("reflex", "Reflexes", "reflexes"))
    elif doc.get("emergency") is not None:
        out.append(_node("reflex", "Reflexes", "emergency"))
    if doc.get("rules") is not None:
        out.append(_node("rules", "Rules", "rules"))
    elif (doc.get("universal") or {}).get("rules") is not None:
        out.append(_node("rules", "Rules", "universal.rules"))

    senses = []
    if isinstance(doc.get("senses"), dict):
        senses += [_node(f"senses.{k}", f"senses › {k}", f"senses.{k}")
                   for k in doc["senses"]]
    uni = doc.get("universal") or {}
    senses += [_node(f"universal.{k}", f"universal › {k}",
                     f"universal.{k}")
               for k in uni if k != "rules"]
    start = doc.get("start") or {}
    senses += [_node(f"start.{k}", f"start › {k}", f"start.{k}")
               for k in start if k not in ("phases", "exit")]
    govern = doc.get("govern") or {}
    senses += [_node(f"govern.{k}", f"govern › {k}", f"govern.{k}")
               for k in govern if k != "goals"]
    if senses:
        out.append(_node("senses", "Senses", None, senses))

    if doc.get("phases") is not None:
        kids = [_node("phases.exit", "init › exit contract",
                      "phases.0.complete")]
        out.append(_node("phases", "Phases", "phases",
                         kids if get_path(doc, "phases.0.complete")
                         else []))
    elif start.get("phases") is not None:
        kids = ([_node("start.exit", "init › exit contract", "start.exit")]
                if start.get("exit") else [])
        out.append(_node("phases", "Phases (init)", "start.phases", kids))
    if doc.get("standing_goals") is not None:
        out.append(_node("goals", "Standing goals", "standing_goals"))
    elif govern.get("goals") is not None:
        out.append(_node("goals", "Standing goals", "govern.goals"))
    if doc.get("options") is not None:
        out.append(_node("options", "Options", "options"))
    elif doc.get("goal_options") is not None:
        out.append(_node("options", "Options", "goal_options"))

    cfg = [_node(f"cfg.{k}", k, k) for k in _CFG_KEYS if k in doc]
    if cfg:
        out.append(_node("cfg", "Config", None, cfg))
    return out


def is_pred(value) -> bool:
    """Predicate-shaped dict (policy.check grammar)."""
    return isinstance(value, dict) and bool(
        {"all", "any", "not", "op", "field"} & set(value))


def is_steps(value) -> bool:
    """A work-unit step list: dicts carrying a template ref."""
    return (isinstance(value, list) and bool(value)
            and all(isinstance(s, dict) and "template" in s
                    for s in value))


def slug_ok(name: str) -> bool:
    return bool(SLUG_RE.match(name or ""))


def save_name_problem(name: str, packs_dir: Path) -> str | None:
    """None when name is writable; else the reason save is refused."""
    if not slug_ok(name):
        return ("name must be a slug: lowercase a-z, 0-9, '-' "
                "(first char a letter or digit)")
    if name == "candidates" or name.startswith("candidates/"):
        return "packs/candidates is owned by the mutate pipeline"
    if not (Path(packs_dir) / name / "pack.yaml").is_file() \
            and not (Path(packs_dir) / f"{name}.yaml").is_file():
        return None  # fresh name
    return "exists"  # caller decides: overwrite-confirm or rename


def save_as_new(doc: dict, name: str, source: str | None,
                packs_dir: Path) -> Path:
    """Write ``packs/<name>/pack.yaml``: pack_id tracks the folder,
    derived_from records lineage, class/revision ride through
    unchanged. The source file is never opened for write."""
    prob = save_name_problem(name, packs_dir)
    if prob and prob != "exists":
        raise ValueError(prob)
    out = dict(doc)
    out["pack_id"] = f"pack.{name}"
    if source:
        out["derived_from"] = source
    path = Path(packs_dir) / name / "pack.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(out, sort_keys=False,
                                   allow_unicode=True),
                    encoding="utf-8")
    return path


def active_pack_id(state_dir: Path) -> str | None:
    """Currently-running pack id per brain_status.json (FR-024)."""
    try:
        s = json.loads((Path(state_dir) / "brain_status.json")
                       .read_text(encoding="utf-8"))
        return s.get("pack_id") or None
    except (OSError, ValueError):
        return None
