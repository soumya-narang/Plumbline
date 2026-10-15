"""JSON-ready views of verdicts, shared by the API, the tools and the static export."""

from __future__ import annotations

from plumbline.policy.verdict import Locked
from plumbline.triage.engine import ArtifactVerdict
from plumbline.triage.receipt import make_receipt


def locked_view(x: Locked) -> dict:
    return {"purl": x.purl, "name": x.name, "version": x.version, "depth": x.depth, "dev": x.dev}


def verdict_view(advisory: str, at_ms: int, v: ArtifactVerdict, with_receipt: bool = True) -> dict:
    """One artifact's verdict for one advisory. The verdict and reason come from the policy, never from prose."""
    r = v.result
    return {
        "artifact": v.artifact,
        "synthetic": v.kind == "planted",
        "service": v.service,
        "tier": v.tier,
        "exposure": v.exposure,
        "verdict": r.verdict,
        "reason": r.reason,
        "evidence": [locked_view(x) for x in r.evidence],
        "assumptions": [{"id": a.fact_id, "kind": a.kind, "key": a.key} for a in r.assumptions],
        "path": list(v.path) if v.path else None,
        "hops": v.hops,
        "receipt": make_receipt(advisory, at_ms, v)["hash"] if with_receipt and r.verdict == "EXPOSED" else None,
    }
