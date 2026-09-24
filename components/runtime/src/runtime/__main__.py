"""CLI: python -m runtime list|probe <id>|discover|bind <role> <ep> <model>|resolve <role> [--live]|loop [--mode run|cycle|improve --game sim|live --stage X] [--iterations N]"""

from __future__ import annotations

import argparse
import json
import sys


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="runtime", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list endpoints + bindings")
    sp = sub.add_parser("probe", help="probe one endpoint")
    sp.add_argument("endpoint")
    sub.add_parser("discover", help="scan well-known local ports")
    sp = sub.add_parser("bind", help="bind role -> endpoint+model")
    sp.add_argument("role"); sp.add_argument("endpoint"); sp.add_argument("model")
    sp = sub.add_parser("resolve", help="resolve a role (offline or live-probed)")
    sp.add_argument("role"); sp.add_argument("--live", action="store_true")
    sp = sub.add_parser("loop", help="unified run loop (sim deterministic)")
    sp.add_argument("--pack", default="core-survival-v0")
    sp.add_argument("--mode", choices=["run", "cycle", "improve"],
                    default="run")
    sp.add_argument("--game", choices=["sim", "live"], default="sim")
    sp.add_argument("--stage", default=None,
                    help="drive only the named phase (debug entry)")
    sp.add_argument("--iterations", type=int, default=5)
    sp.add_argument("--bridge", default="http://127.0.0.1:8765")
    sp.add_argument("--live-flag", action="store_true",
                    help="confirm live mode (operator smoke only)")
    sp.add_argument("--ledger", action="store_true",
                    help="reconcile the task ledger before attend each poll")
    sp.add_argument("--feed", action="store_true",
                    help="narrate every emitted event into state/feed.md")
    sp.add_argument("--fair", dest="fair", action="store_true", default=True,
                    help="fair run (default): refuse dev.* and save/load "
                         "(UR-CTL-009)")
    sp.add_argument("--dev", dest="fair", action="store_false",
                    help="development testing only: allow dev/cheat surface")
    sp.add_argument("--no-store", action="store_true",
                    help="do not persist events to state/events.jsonl")
    sp.add_argument("--live-brain", action="store_true",
                    help="honor brain-reset requests mid-run")
    sp.add_argument("--no-hold", action="store_true",
                    help="start mode: stop at start.completed")
    sp = sub.add_parser("plan", help="planner/review loop (sim deterministic)")
    sp.add_argument("--pack", default="core-survival-v0")
    sp.add_argument("--mode", choices=["sim", "live"], default="sim")
    sp.add_argument("--iterations", type=int, default=1)
    sp.add_argument("--bridge", default="http://127.0.0.1:8765")
    sp.add_argument("--no-dispatch", action="store_true")
    sp.add_argument("--live-flag", action="store_true",
                    help="confirm live mode (operator only)")
    sp.add_argument("--dev", dest="fair", action="store_false", default=True,
                    help="development testing only: allow dev/cheat surface")
    args = p.parse_args(argv)

    from . import bindings as _b, discover as _d, probe as _p, registry as _r

    if args.cmd == "list":
        _print({"endpoints": _r.load_endpoints(),
                "bindings": _r.load_bindings()})
    elif args.cmd == "probe":
        _print(_p.probe_endpoint(args.endpoint))
    elif args.cmd == "discover":
        _print(_d.scan_local())
    elif args.cmd == "bind":
        _print(_r.set_binding(args.role, args.endpoint, args.model))
    elif args.cmd == "resolve":
        _print(_b.resolve_role(args.role, probe_live=args.live))
    elif args.cmd == "loop":
        from . import loop as _loop
        return _loop.main(["--pack", args.pack, "--mode", args.mode,
                           "--game", args.game,
                           "--iterations", str(args.iterations),
                           "--bridge", args.bridge]
                          + (["--stage", args.stage] if args.stage else [])
                          + (["--live"] if args.live_flag else [])
                          + (["--ledger"] if args.ledger else [])
                          + (["--feed"] if args.feed else [])
                          + ([] if args.fair else ["--dev"])
                          + (["--no-store"] if args.no_store else [])
                          + (["--live-brain"] if args.live_brain else [])
                          + (["--no-hold"] if args.no_hold else []))
    elif args.cmd == "plan":
        from . import planloop as _pl
        return _pl.main(["--pack", args.pack, "--mode", args.mode,
                         "--iterations", str(args.iterations),
                         "--bridge", args.bridge]
                        + (["--no-dispatch"] if args.no_dispatch else [])
                        + (["--live"] if args.live_flag else [])
                        + ([] if args.fair else ["--dev"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
