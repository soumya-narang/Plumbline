"""Command line entry point: ``python -m plumbline <command>``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from plumbline.graph.client import connect, run_named
from plumbline.graph.loader import load_all
from plumbline.ingest.fleet import pin_fleet, refresh_planted
from plumbline.ingest.lockgraph import build_all
from plumbline.ingest.osv import fetch_advisories
from plumbline.memory.replay import seek
from plumbline.timeutil import now_ms, to_iso, to_ms
from plumbline.triage.engine import triage_advisory
from plumbline.triage.receipt import make_receipt, verify


def _cmd_pin_fleet(args: argparse.Namespace) -> None:
    refresh_planted() if args.planted_only else pin_fleet()


def _cmd_build_data(_: argparse.Namespace) -> None:
    advisories = fetch_advisories()
    print(f"advisories: {len(advisories)}")
    for stat in build_all():
        print(f"{stat['artifact']:30} deps={stat['deps']:<5} edges={stat['edges']}")


def _cmd_load(_: argparse.Namespace) -> None:
    for name, n in load_all().items():
        print(f"{name:18} {n}")


def _cmd_query(args: argparse.Namespace) -> None:
    params = dict(p.split("=", 1) for p in args.param)
    result = run_named(connect(), args.name, params)
    print(json.dumps({"header": [h[1] for h in result.header], "rows": result.result_set}, default=str, indent=1))


def _cmd_triage(args: argparse.Namespace) -> None:
    at_ms = to_ms(args.at) if args.at else now_ms()
    graph = connect()
    report = triage_advisory(graph, args.advisory, at_ms)
    if report is None:
        raise SystemExit(f"{args.advisory} is not published at {to_iso(at_ms)}")
    print(f"{args.advisory} ({report.advisory.package}) at {to_iso(at_ms)}: {report.counts()}")
    for v in report.verdicts:
        if v.result.verdict == "CLEARED" and not args.all:
            continue
        detail = " > ".join(v.path) if v.path else ", ".join(x.purl for x in v.result.evidence) or v.result.reason
        print(f"  {v.result.verdict:8} {v.artifact:30} {v.exposure or '-':9} {detail}")
        if args.receipts:
            receipt = make_receipt(args.advisory, at_ms, v)
            out = Path(args.receipts)
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{args.advisory}__{v.artifact.replace('/', '__')}.json").write_text(
                json.dumps(receipt, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _cmd_replay(args: argparse.Namespace) -> None:
    state = seek(connect(), to_ms(args.to))
    print(f"replay to {args.to}: {len(state.applied)} events applied")
    for e in state.applied:
        tag = " [SCRIPTED]" if e.get("scripted") else ""
        print(f"  {e['at']}  {e['type']}{tag}  {e.get('artifact', '')} {e['advisory']}")
    print("decisions:")
    for d in state.decisions:
        print(f"  {d['status']:9} {d['verdict']:8} {d['artifact']:28} {d['advisory']}")
    for r in state.reopened:
        print(f"REOPENED {r.artifact}: was {r.before}, now {r.now.result.verdict}; broken: {', '.join(r.broken)}")


def _cmd_export_static(_: argparse.Namespace) -> None:
    from plumbline.export_static import DEFAULT_OUT, export

    n = export()
    print(f"exported {n} timeline stops to {DEFAULT_OUT}")


def _cmd_benchmark(_: argparse.Namespace) -> None:
    from plumbline.bench.run import main

    main()


def _cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run("plumbline.api.app:app", host=args.host, port=args.port)


def _cmd_verify(args: argparse.Namespace) -> None:
    receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
    ok, why = verify(connect(), receipt)
    print(("VERIFIED: " if ok else "FAILED: ") + why)
    raise SystemExit(0 if ok else 1)


def main() -> None:
    parser = argparse.ArgumentParser(prog="plumbline")
    sub = parser.add_subparsers(dest="command", required=True)

    pin = sub.add_parser("pin-fleet", help="pin repositories to the incident time and record lockfile hashes")
    pin.add_argument("--planted-only", action="store_true", help="only refresh the hand-authored fixtures")
    sub.add_parser("build-data", help="fetch advisories and write processed JSONL")
    sub.add_parser("load", help="rebuild the FalkorDB graph from processed JSONL")

    q = sub.add_parser("query", help="run a named query from queries/")
    q.add_argument("name")
    q.add_argument("-p", "--param", action="append", default=[], metavar="KEY=VALUE")

    t = sub.add_parser("triage", help="evaluate every artifact against one advisory")
    t.add_argument("advisory")
    t.add_argument("--at", help="ISO time to evaluate at (default: now)")
    t.add_argument("--all", action="store_true", help="also list CLEARED artifacts")
    t.add_argument("--receipts", metavar="DIR", help="write a receipt JSON per listed artifact")

    r = sub.add_parser("replay", help="replay recorded approvals and scripted events up to a time")
    r.add_argument("--to", required=True, help="ISO time to replay to")

    sub.add_parser("export-static", help="write the incident as static JSON for the serverless site")

    sub.add_parser("benchmark", help="grade the graph, SQL and naive retrieval against npm's own resolver")

    sv = sub.add_parser("serve", help="serve the UI and API")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)

    v = sub.add_parser("verify", help="re-derive a receipt from the graph and check it")
    v.add_argument("receipt", help="path to a receipt JSON")

    args = parser.parse_args()
    {"pin-fleet": _cmd_pin_fleet, "build-data": _cmd_build_data, "load": _cmd_load, "query": _cmd_query,
     "triage": _cmd_triage, "replay": _cmd_replay, "verify": _cmd_verify,
     "serve": _cmd_serve, "export-static": _cmd_export_static,
     "benchmark": _cmd_benchmark}[args.command](args)


if __name__ == "__main__":
    main()
