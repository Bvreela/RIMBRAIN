# bridgecheck

Standalone connectivity test for RimWorld bridge mods — no repo dependencies, stdlib-only Python.

```powershell
python tools/bridgecheck/bridge_check.py            # probe both protocols
python tools/bridgecheck/bridge_check.py --only gabp --json
python tools/bridgecheck/bridge_check.py --token HEX
```

## What it checks

| Bridge | Port | Checks |
|---|---|---|
| zorrobyte RimBridge (HTTP JSON-RPC) | 8765 | `/health`, `/methods` inventory, `rpc state.summary`, `/events` feed |
| pardeike RimBridgeServer (GABP) | 5174 | TCP connect, `session/hello` auth, `tools/list`, `rimbridge/ping`, `get_game_info` |

The GABP token is resolved from `--token`, then `$env:GABP_TOKEN`, then the latest
`Bridge token:` line in `Player.log` — normally zero-config while the game is running.

Exit code `0` = at least one bridge fully verified, `1` = none reachable. `--json` emits a
machine-readable report for CI gates (TE-015 health gate).
