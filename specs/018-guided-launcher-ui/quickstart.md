# Quickstart: Guided Launcher UI validation

Prereqs: repo checkout, `PYTHONPATH=components/runtime/src;components/contracts/src;components/dashboard/src` (dev), bridge not required for sim/screens.

## 1. Menu entry & defaults (FR-001..005)

```powershell
python rimbrain.py            # or: python rimbrain.py run
```

Expect: setup screen opens — every loop flag has a control; fair on, mode
`start`, pack `start-mode-v0`, live/live-brain/live-mutate/feed checked,
iterations 2000. Assembled argv preview visible.

```powershell
python rimbrain.py run -y     # instant fair pass, no menu (loop needs bridge)
python rimbrain.py run --mode sim --iterations 3   # headless, no menu
python rimbrain.py run -y --mode sim               # usage error, exit 2
```

## 2. Constraint mirror (FR-004)

On the setup screen: pick mode `cycle` with fair on → GO blocked, reason
shown. Enable live-mutate with mode `improve` → blocked. Pick `dev-lab-v0`
with fair on → refused. Uncheck fair → dev pack selectable.

## 3. Brain checks (FR-006..010)

With Laya serving (`tools/serve-laya.ps1`) and `OPENROUTER_API_KEY` set:
brains rows show `local-laya · laya` and `openrouter · nemotron-…` with
green answered verdicts + latency. Kill Laya → re-check → row turns
unreachable + fallback note; screen stayed responsive throughout; GO still
available.

Unit-level (no endpoints): `uv run pytest components/runtime/tests/test_probe_live.py`
— verdict matrix against stubbed transports.

## 4. Pack list & swap (FR-011..013)

Packs list shows all `packs/` entries with `[fair]`/`[dev]` badges.
Mid-run: pick another fair pack → Use → `brain_status.json` reports the
swap (existing channel).

## 5. Guided editor (FR-014..020,024)

Setup → Edit Pack on `start-mode-v0`:

- Outline shows Capabilities / Reflexes / Senses / Phases / Rules /
  Standing goals.
- Open Phases › shelter: form shows id/requires/lease/attempts; effect
  renders in the predicate builder; steps list `build-layout` with
  schema-generated param rows.
- Change `lease_ticks` to 11000 → Save → name dialog prefilled
  `start-mode-v0-custom` → save → validation passes →
  `packs/start-mode-v0-custom/pack.yaml` exists with `pack_id:
  pack.start-mode-v0-custom` and `derived_from: start-mode-v0`;
  `start-mode-v0/pack.yaml` byte-identical (hash check).
- Deliberately break a template id → Save → blocked, issues listed.
- Raw tab still opens the YAML text view.

## 6. Run lifecycle (FR-021..023)

GO → monitor shows run + "running". Setup re-opened → argv controls
read-only, pack/brains live. Stop → loop exits, status shows it.
Edit iterations → Restart → confirm → new run with new argv. Close window
mid-run → no orphan `runtime loop` process remains
(`Get-Process python` / tasklist check).

## 7. Frozen parity

`tools/build-exe.ps1` → `dist\rimbrain.exe` behaves identically: menu,
GO spawns loop child via `RIMBRAIN_LOOP_CMD`, packs/ resolves beside exe.

## Test suites

```powershell
uv run pytest components/dashboard/tests -q   # +paramspec/brains/packedit
uv run pytest components/runtime/tests -q     # +probe_live
```
