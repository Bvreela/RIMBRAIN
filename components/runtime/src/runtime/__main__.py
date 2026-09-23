"""CLI: python -m runtime list|probe <id>|discover|bind <role> <ep> <model>|resolve <role> [--live]|loop [--mode sim|live] [--iterations N]"""

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
    sp = sub.add_parser("loop", help="dispatcher poll loop (sim deterministic)")
    sp.add_argument("--pack", default="core-survival-v0")
    sp.add_argument("--mode", choices=["sim", "live", "start"], default="sim")
    sp.add_argument("--iterations", type=int, default=5)
    sp.add_argument("--bridge", default="http://127.0.0.1:8765")
    sp.add_argument("--live-flag", action="store_true",
                    help="confirm live mode (operator smoke only)")
    sp.add_argument("--ledger", action="store_true",
                    help="reconcile the task ledger before attend each poll")
    sp = sub.add_parser("plan", help="planner/review loop (sim deterministic)")
    sp.add_argument("--pack", default="core-survival-v0")
    sp.add_argument("--mode", choices=["sim", "live"], default="sim")
    sp.add_argument("--iterations", type=int, default=1)
    sp.add_argument("--bridge", default="http://127.0.0.1:8765")
    sp.add_argument("--no-dispatch", action="store_true")
    sp.add_argument("--live-flag", action="store_true",
                    help="confirm live mode (operator only)")
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
                           "--iterations", str(args.iterations),
                           "--bridge", args.bridge]
                          + (["--live"] if args.live_flag else [])
                          + (["--ledger"] if args.ledger else []))
    elif args.cmd == "plan":
        from . import planloop as _pl
        return _pl.main(["--pack", args.pack, "--mode", args.mode,
                         "--iterations", str(args.iterations),
                         "--bridge", args.bridge]
                        + (["--no-dispatch"] if args.no_dispatch else [])
                        + (["--live"] if args.live_flag else []))
    return 0


if __name__ == "__main__":
    sys.exit(main())
