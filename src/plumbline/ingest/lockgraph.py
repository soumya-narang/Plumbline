"""Turn each pinned lockfile into versioned, hashed JSONL under ``data/processed``.

The JSONL files are the contract between ingestion and the graph loader: the demo loads from them and
never depends on a live API. Output is deterministic, so identical input yields byte-identical files.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from plumbline import config
from plumbline.ingest.fleet import FleetEntry, load_fleet, verify_lockfile
from plumbline.ingest.npm_lock import LockGraph, parse_npm_lock

LOCKGRAPH_DIR = config.PROCESSED / "lockgraph"
MANIFEST_PATH = config.PROCESSED / "MANIFEST.json"


def lockgraph_path(entry: FleetEntry):
    return LOCKGRAPH_DIR / f"{entry.slug}.jsonl"


def rows_for(artifact_id: str, graph: LockGraph) -> list[dict]:
    """The loader's JSONL rows for one parsed lockfile: one ``dep`` per install, one ``requires`` per edge."""
    lines = []
    for key in sorted(graph.deps):
        lines.append({"t": "dep", "artifact": artifact_id, "id": f"{artifact_id}::{key}", **asdict(graph.deps[key])})
    for src, dst in graph.edges:
        lines.append({"t": "requires", "artifact": artifact_id, "from": f"{artifact_id}::{src}", "to": f"{artifact_id}::{dst}"})
    return lines


def build_lockgraph(entry: FleetEntry) -> dict:
    graph = parse_npm_lock(verify_lockfile(entry))
    lines = rows_for(entry.id, graph)
    LOCKGRAPH_DIR.mkdir(parents=True, exist_ok=True)
    lockgraph_path(entry).write_text(
        "".join(json.dumps(line, sort_keys=True) + "\n" for line in lines), encoding="utf-8", newline="\n")
    return {"artifact": entry.id, "deps": len(graph.deps), "edges": len(graph.edges)}


def build_all() -> list[dict]:
    stats = [build_lockgraph(e) for e in load_fleet() if e.lock_state == "present"]
    write_manifest()
    return stats


def write_manifest() -> None:
    files = sorted(p for p in config.PROCESSED.rglob("*.jsonl"))
    manifest = {
        str(p.relative_to(config.PROCESSED)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in files
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
