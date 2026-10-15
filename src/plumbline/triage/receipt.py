"""Hash-checked receipts: a verdict that anyone can re-derive from the same data.

A receipt records the verdict, its evidence and path, the exact text of the queries that produced it, and the hash of
the data it was computed from. ``verify`` re-runs the evidence queries and the policy and compares hashes.
"""

from __future__ import annotations

import hashlib
import json

from falkordb import Graph

from plumbline import config
from plumbline.graph.client import read_query_text
from plumbline.policy.verdict import POLICY_VERSION
from plumbline.triage.engine import ArtifactVerdict, triage_artifact

QUERIES_USED = ("triage/advisory_at", "triage/relevant_locks", "triage/artifacts", "q2_explain_path")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def data_hash() -> str:
    """Hash of the committed inputs the graph is built from."""
    parts = [config.PROCESSED / "MANIFEST.json", config.DATA / "fleet.json", config.DATA / "overlay.json"]
    return _sha(b"".join(_sha(p.read_bytes()).encode() for p in parts))


def _payload(advisory: str, at_ms: int, v: ArtifactVerdict) -> dict:
    return {
        "policy_version": POLICY_VERSION,
        "advisory": advisory,
        "artifact": v.artifact,
        "at_ms": at_ms,
        "verdict": v.result.verdict,
        "reason": v.result.reason,
        "evidence": [x.purl for x in v.result.evidence],
        "assumptions": [a.fact_id for a in v.result.assumptions],
        "path": list(v.path) if v.path else None,
        "query_sha256": {q: _sha(read_query_text(q).encode()) for q in QUERIES_USED},
        "data_sha256": data_hash(),
    }


def payload_hash(payload: dict) -> str:
    return _sha(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())


def make_receipt(advisory: str, at_ms: int, v: ArtifactVerdict) -> dict:
    payload = _payload(advisory, at_ms, v)
    return {"payload": payload, "hash": payload_hash(payload)}


def verify(graph: Graph, receipt: dict) -> tuple[bool, str]:
    p = receipt["payload"]
    # 1. The payload must match the hash it claims, otherwise it was edited after issue.
    if payload_hash(p) != receipt["hash"]:
        return False, "payload does not match its hash (the receipt was altered)"
    # 2. Re-derive the verdict from the graph and compare field by field.
    current = triage_artifact(graph, p["advisory"], p["artifact"], p["at_ms"])
    if current is None:
        return False, "advisory is not visible at the receipt's time"
    rebuilt = make_receipt(p["advisory"], p["at_ms"], current)
    if rebuilt["hash"] == receipt["hash"]:
        return True, "verdict, evidence, queries and data all match"
    diffs = [k for k in p if p[k] != rebuilt["payload"].get(k)]
    return False, "differs from a fresh derivation in: " + ", ".join(diffs)
