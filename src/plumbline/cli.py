"""Command line entry point: ``python -m plumbline <command>``."""

from __future__ import annotations

import argparse
import json

from plumbline.graph.client import connect, run_named
from plumbline.graph.loader import load_all
from plumbline.ingest.fleet import pin_fleet, refresh_planted
from plumbline.ingest.lockgraph import build_all
from plumbline.ingest.osv import fetch_advisories


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
    args = parser.parse_args()
    {"pin-fleet": _cmd_pin_fleet, "build-data": _cmd_build_data, "load": _cmd_load, "query": _cmd_query}[args.command](args)


if __name__ == "__main__":
    main()
