# Contract: Launch command surface + loop-spawn env

**Feature**: 018 | **Producer**: `rimbrain.py` | **Consumers**: operator,
`dashboard.overlay` (loop child spawn)

## Command surface

```text
rimbrain                     → overlay, setup screen (menu)
rimbrain run                 → overlay, setup screen (menu)
rimbrain run -y | --yes      → immediate fair-defaults pass (today's
                               no-arg behavior; for scripts/muscle memory)
rimbrain run <any loop flag> → headless: overlay + loop with those args,
                               exactly as today
rimbrain loop <args>         → unchanged (runtime loop pass-through)
rimbrain overlay <args>      → unchanged (overlay child entry)
```

### Rules

- `-y`/`--yes` is valid ONLY as the sole argument to `run`; combined with
  other flags it is a usage error (exit 2, docstring printed).
- Menu mode and headless mode share the overlay spawn path — the only
  difference is whether the window opens on Setup or Monitor.
- Every `runtime loop` flag continues to pass through verbatim in headless
  mode; the menu is additive, not a filter.

## `RIMBRAIN_LOOP_CMD` env var

Set by `rimbrain.py` on the overlay child's environment. Value: a **JSON
argv array** — the prefix the overlay prepends to the assembled flag list
when spawning the loop child.

```jsonc
// frozen
["J:\\RimAgent\\rimbrainagent\\dist\\rimbrain.exe", "loop"]
// dev
["C:\\...\\python.exe", "-m", "runtime", "loop"]
```

### Rules

- JSON array of strings; parsed with `json.loads`; malformed/missing →
  GO disabled with an explanatory label (standalone-overlay case).
- The overlay appends ONLY flag args (`--mode`, `--pack`, …) — never
  positional args — so the prefix always terminates at `loop`.
- Spawned child inherits the overlay's environment (`RIMBRAIN_STATE_DIR`,
  `PYTHONPATH`) — same propagation as today's spawn path.
- The overlay owns the child: `proc.poll()` on the refresh cadence; window
  close ⇒ `proc.terminate()` (then kill on timeout).

## Assembled argv (menu → loop child)

`RIMBRAIN_LOOP_CMD + ["--pack", pack, "--mode", mode, "--iterations", N,
"--bridge", url] + flag args` where flag args are emitted only when set:

| Control | Emitted arg(s) |
|---|---|
| fair on | `--fair` |
| fair off | `--dev` |
| live | `--live-flag` |
| live_brain | `--live-brain` |
| live_mutate | `--live-mutate` |
| feed | `--feed` |
| ledger | `--ledger` |
| no_store | `--no-store` |
| no_hold | `--no-hold` |

Defaults emit the same argv as today's no-arg `run` preset, so a default
menu GO is byte-equivalent to `rimbrain run -y`.
