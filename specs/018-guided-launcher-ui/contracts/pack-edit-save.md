# Contract: Guided editor save artifact + active-pack overwrite

**Feature**: 018 | **Producer**: `dashboard.packedit` |
**Consumers**: `templates.load_pack` (reader), launcher pack list

## Save-as-new (normal path)

Guided save writes ONE new file; the source pack is never modified.

```text
packs/<name>/pack.yaml          # <name> slug: [a-z0-9-]+, unique under packs/
```

Document requirements on write:

| Field | Rule |
|---|---|
| `pack_id` | `pack.<name>` — updated to match the new folder |
| `derived_from` | source pack id (additive optional metadata) |
| `class` | copied from source unchanged (fair/dev gating preserved) |
| `revision`/`policy_version`/`schema_version` | copied unchanged |
| everything else | the edited doc |

**Schema amendment required**: `pack.schema.json` root is
`additionalProperties: false` — this feature adds one optional property
`"derived_from": {"type": "string"}` to
`components/contracts/schemas/runtime/pack.schema.json`. Additive-optional:
existing packs still validate; the field rides the pack hash like any other.

### Rules

- Pre-write: `api.validate_pack_doc(doc)` MUST return `{ok:true}` — save is
  blocked with issues listed otherwise.
- Name collision: prompt — choose another name or confirm overwrite of the
  *user* pack (never blocked silently). Blank/invalid slug ⇒ cannot save.
- Forbidden target: `packs/candidates/` — owned by the mutate pipeline.
- Post-write: pack list rescans; the new pack is auto-selected.
- Save-as-new on the ACTIVE pack's source is always safe — the active pack
  file itself is untouched, so no drift.

## Overwrite-active (confirmed path)

Available only when the edited doc's `pack_id`/path is the currently
running pack (per `brain_status.json`):

1. Warn: "overwrites the live brain — the run hot-swaps to this version."
2. Write file in place.
3. Immediately post `state/brain_reset.request` `{}` — the runtime reloads
   the pack (`load_pack` re-reads → new hash → drift resolved within one
   poll).

Editing or overwriting a NON-active pack never posts a reset and never
freezes the run.

## Outline vocabulary map (v0 paths → labels)

| On-disk path | Outline label |
|---|---|
| `templates` | Capabilities |
| `emergency` | Reflexes |
| `universal.rules` | Rules |
| `universal.*` (other) | Senses |
| `start.*` cfg blocks | Senses › start |
| `start.phases` | Phases (init) |
| `start.exit` | Phases (init) › exit contract |
| `govern.*` cfg | Senses › govern |
| `govern.goals` | Standing goals |
| `goal_options` | Options |
| `jobs`, `decision_map` | hidden (dead fields, dropped in v1) |

When feature 017's v1 loader lands, this map is the only editor surface
that changes — forms and save semantics are unchanged.

**Forward-compat**: `decide`/`reflexes`/`rules`/`standing_goals` v1 paths
have no v0 on-disk equivalent — the outline shows those sections only when
the loaded doc actually contains them (post-017 packs). v0 packs simply
omit them; this is expected, not a gap.
