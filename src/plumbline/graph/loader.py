"""Load the processed JSONL files into FalkorDB. Idempotent: the graph is rebuilt from scratch."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from itertools import islice

from falkordb import Graph

from plumbline import config
from plumbline.graph.client import connect, run_named
from plumbline.graph.schema import apply_schema
from plumbline.ingest.fleet import FleetEntry, load_fleet
from plumbline.ingest.lockgraph import lockgraph_path
from plumbline.ingest.osv import load_advisories

BATCH = 500


def _batches(rows: Iterable[dict], size: int = BATCH) -> Iterator[list[dict]]:
    it = iter(rows)
    while chunk := list(islice(it, size)):
        yield chunk


def _run_batched(graph: Graph, query: str, rows: Iterable[dict]) -> int:
    n = 0
    for chunk in _batches(rows):
        run_named(graph, query, {"rows": chunk}, read_only=False)
        n += len(chunk)
    return n


def _read_jsonl(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _overlay_rows(fleet: list[FleetEntry]) -> list[dict]:
    overlay = json.loads((config.DATA / "overlay.json").read_text(encoding="utf-8"))["services"]
    rows = []
    for e in fleet:
        if e.id not in overlay:
            continue
        o = overlay[e.id]
        rows.append({
            "artifact": e.id, "service_id": f"svc:{o['service']}", "name": o["service"], "tier": o["tier"],
            "exposure_id": f"exp:{o['service']}", "exposure": o["exposure"],
        })
    return rows


def load_all(graph_name: str = "plumbline") -> dict[str, int]:
    graph = connect(graph_name)
    try:
        graph.delete()
    except Exception:  # the graph does not exist yet
        pass
    apply_schema(graph)

    fleet = load_fleet()
    counts: dict[str, int] = {}
    counts["advisories"] = _run_batched(graph, "load/advisory", load_advisories())
    counts["artifacts"] = _run_batched(graph, "load/artifact", (
        {"id": e.id, "kind": e.kind, "sha": e.sha, "committed_at": e.committed_at, "lockfile": e.lockfile,
         "lock_state": e.lock_state, "lock_sha256": e.lockfile_sha256, "synthetic": e.kind == "planted"} for e in fleet))
    counts["services"] = _run_batched(graph, "load/service_overlay", _overlay_rows(fleet))

    deps = edges = members = 0
    for e in fleet:
        if e.lock_state != "present":
            continue
        rows = _read_jsonl(lockgraph_path(e))
        dep_rows = [r for r in rows if r["t"] == "dep"]
        third_party = [r for r in dep_rows if not r["workspace"]]
        workspace = [r for r in dep_rows if r["workspace"]]
        deps += _run_batched(graph, "load/locked_dep", third_party)
        members += _run_batched(graph, "load/workspace_member", workspace)
        edges += _run_batched(graph, "load/requires", (r for r in rows if r["t"] == "requires"))
    counts.update(locked_deps=deps, workspace_members=members, requires_edges=edges)
    return counts
