"""The agent's tools: plain, typed, read-only functions over the graph.

Every function returns JSON-ready data. None of them writes to the graph: proposing a decision describes it,
and committing one is a separate, human-approved path (``plumbline.memory.decisions.commit``) that is not a tool.
Verdicts in these results come from the deterministic policy; the model can quote them but never alter them.
"""

from __future__ import annotations

from falkordb import Graph

from plumbline.graph.client import connect, run_named
from plumbline.memory.decisions import ACTIONS, propose
from plumbline.snapshot import advisories_at
from plumbline.timeutil import to_iso, to_ms
from plumbline.triage.engine import triage_advisory, triage_artifact
from plumbline.triage.serialize import locked_view, verdict_view

_graph: Graph | None = None


def graph() -> Graph:
    global _graph
    if _graph is None:
        _graph = connect()
    return _graph


def list_advisories(at: str) -> dict:
    """List the malicious-package advisories published at or before the given UTC time (ISO 8601)."""
    return {"at": at, "advisories": advisories_at(graph(), to_ms(at))}


def triage_advisory_tool(advisory: str, at: str, include_cleared: bool = False) -> dict:
    """Evaluate every artifact in the fleet against one advisory as known at the given time.

    Returns counts of EXPOSED, UNKNOWN and CLEARED artifacts and the rows that need attention. EXPOSED rows carry
    the dependency path and a receipt hash; UNKNOWN rows say what evidence is missing. CLEARED rows are omitted
    unless include_cleared is true.
    """
    at_ms = to_ms(at)
    report = triage_advisory(graph(), advisory, at_ms)
    if report is None:
        return {"error": f"{advisory} is not published at {at}, or does not exist"}
    rows = [verdict_view(advisory, at_ms, v) for v in report.verdicts
            if include_cleared or v.result.verdict != "CLEARED"]
    return {"advisory": advisory, "package": report.advisory.package, "at": at, "counts": report.counts(),
            "affected_versions": sorted(report.advisory.affected_purls), "rows": rows}


def explain_path(advisory: str, artifact: str, at: str) -> dict:
    """Explain one artifact's verdict for one advisory: the evidence, the dependency path and the assumptions."""
    at_ms = to_ms(at)
    v = triage_artifact(graph(), advisory, artifact, at_ms)
    if v is None:
        return {"error": f"no verdict for {artifact} against {advisory} at {at}"}
    return {"advisory": advisory, "at": at, **verdict_view(advisory, at_ms, v)}


def reopen_check(at: str) -> dict:
    """Find decisions whose assumptions have since been contradicted (read-only).

    `state` is "pending" for an accepted decision that now has a broken assumption and "reopened" for one already
    marked reopened.
    """
    at_ms = to_ms(at)
    out = []
    for state, query in (("pending", "q5_reopen_check"), ("reopened", "memory/reopened_decisions")):
        for d, verdict, adv, art, broken, ms in run_named(graph(), query, {"at_ms": at_ms}).result_set:
            out.append({"decision": d, "state": state, "decided_verdict": verdict, "advisory": adv, "artifact": art,
                        "broken_assumptions": sorted(broken), "broken_at": to_iso(ms)})
    return {"at": at, "decisions": sorted(out, key=lambda x: x["decision"])}


def propose_decision(advisory: str, artifact: str, at: str) -> dict:
    """Describe the decision that would be recorded for this pair. Writes nothing; a human must approve it."""
    at_ms = to_ms(at)
    try:
        p = propose(graph(), advisory, artifact, at_ms)
    except LookupError as exc:
        return {"error": str(exc)}
    r = p.verdict.result
    return {
        "advisory": advisory, "artifact": artifact, "at": at, "verdict": r.verdict, "reason": r.reason,
        "proposed_action": ACTIONS[r.verdict], "evidence": [locked_view(x) for x in r.evidence],
        "would_assume": [{"id": a.fact_id, "kind": a.kind, "key": a.key} for a in r.assumptions],
        "path": list(p.verdict.path) if p.verdict.path else None,
        "written": False, "requires_human_approval": True,
    }


def fix_first(advisory: str, at: str) -> dict:
    """Rank the direct dependencies to upgrade first: which ones drag the affected versions into the most artifacts."""
    rows = run_named(graph(), "q6_fix_first", {"advisory": advisory, "at_ms": to_ms(at)}).result_set
    return {"advisory": advisory, "at": at, "bump": [
        {"package": f"{name}@{version}", "artifacts": n, "in_artifacts": sorted(where)} for name, version, n, where in rows]}


def critical_dependencies(artifact: str, limit: int = 8) -> dict:
    """The packages an artifact leans on most, by PageRank over its dependency graph. A compromise of a highly ranked
    package reaches the most of the tree."""
    rows = run_named(graph(), "q7_critical_dependencies",
                     {"prefix": f"{artifact}::", "limit": max(1, min(int(limit), 25))}).result_set
    return {"artifact": artifact, "ranked_by": "PageRank over REQUIRES", "packages": [
        {"package": f"{name}@{version}", "score": round(score, 6)} for name, version, score in rows]}


def list_decisions() -> dict:
    """List recorded decisions with their status (accepted or reopened)."""
    from plumbline.memory.decisions import list_decisions as _list

    return {"decisions": [{**d, "created": to_iso(d["created_ms"])} for d in _list(graph())]}


# name -> function. The MCP server registers exactly these, under these names.
TOOLS = {
    "list_advisories": list_advisories,
    "triage_advisory": triage_advisory_tool,
    "explain_path": explain_path,
    "reopen_check": reopen_check,
    "propose_decision": propose_decision,
    "fix_first": fix_first,
    "critical_dependencies": critical_dependencies,
    "list_decisions": list_decisions,
}
