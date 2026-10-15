"""A snapshot is everything the UI needs to draw one moment of the incident.

The live API and the static export both produce this exact shape, so one front-end serves both.
"""

from __future__ import annotations

import os

from falkordb import Graph

from plumbline.agent.suggestions import SUGGESTIONS
from plumbline.graph.client import read_query_text, run_named
from plumbline.ingest.fleet import load_incident
from plumbline.memory.replay import ReplayState, load_events, seek
from plumbline.timeutil import to_iso, to_ms
from plumbline.triage.engine import triage_advisory
from plumbline.triage.serialize import verdict_view


def advisories_at(graph: Graph, at_ms: int) -> list[dict]:
    rows = run_named(graph, "triage/advisories_at", {"at_ms": at_ms}).result_set
    return [{"id": a, "package": p, "published_ms": ms, "published": to_iso(ms), "summary": s} for a, p, ms, s in rows]


def timeline(graph: Graph) -> list[dict]:
    """Ordered, labelled stops: the incident's start, each advisory publication and each replay event."""
    incident = load_incident()
    stops = [{"at": incident["as_of"], "kind": "start", "label": "Before the first release", "scripted": False}]
    for adv in advisories_at(graph, to_ms(incident["as_of"]) + 10**9):  # every advisory in the incident
        stops.append({"at": adv["published"], "kind": "advisory", "label": f"{adv['package']} published",
                      "advisory": adv["id"], "scripted": False})
    for e in load_events():
        if e["type"] == "approve":
            stops.append({"at": e["at"], "kind": "approval", "label": f"Approved {e['artifact']}",
                          "advisory": e["advisory"], "artifact": e["artifact"], "scripted": False})
        else:
            stops.append({"at": e["at"], "kind": "revision", "label": "Advisory revised (hypothetical)",
                          "advisory": e["advisory"], "scripted": bool(e.get("scripted")), "note": e.get("note", "")})
    stops.sort(key=lambda s: (to_ms(s["at"]), {"start": 0, "advisory": 1, "approval": 2, "revision": 3}[s["kind"]]))
    for i, s in enumerate(stops):
        s["index"] = i
        s["at_ms"] = to_ms(s["at"])
    return stops


def _event_view(e: dict) -> dict:
    return {"at": e["at"], "type": e["type"], "scripted": bool(e.get("scripted")), "advisory": e["advisory"],
            "artifact": e.get("artifact"), "add_purls": e.get("add_purls"), "note": e.get("note", ""),
            "approver": e.get("approver"), "manual": bool(e.get("manual"))}


def snapshot(graph: Graph, at_ms: int, extra: list[dict] | None = None) -> dict:
    state: ReplayState = seek(graph, at_ms, extra)
    decisions = {(d["advisory"], d["artifact"]): d for d in state.decisions}
    advisories = []
    for adv in advisories_at(graph, at_ms):
        report = triage_advisory(graph, adv["id"], at_ms)
        rows = []
        for v in report.verdicts:
            row = verdict_view(adv["id"], at_ms, v)
            d = decisions.get((adv["id"], v.artifact))
            row["decision"] = {"id": d["decision"], "status": d["status"], "verdict": d["verdict"]} if d else None
            rows.append(row)
        advisories.append({**adv, "counts": report.counts(), "affected_purls": sorted(report.advisory.affected_purls),
                           "rows": rows})
    return {
        "at": to_iso(at_ms),
        "at_ms": at_ms,
        "incident": load_incident()["name"],
        "events": [_event_view(e) for e in state.applied],
        "advisories": advisories,
        "decisions": [{**d, "created": to_iso(d["created_ms"])} for d in state.decisions],
        "reopened": [{
            "decision": r.decision, "advisory": r.advisory, "artifact": r.artifact, "before": r.before,
            "now": r.now.result.verdict, "reason": r.now.result.reason, "broken": list(r.broken),
            "broken_at": to_iso(r.broken_ms),
        } for r in state.reopened],
    }


def build_meta(graph: Graph) -> dict:
    """What the UI needs before it can draw anything. Shared by the live API and the static export."""
    return {
        "incident": load_incident(),
        "timeline": timeline(graph),
        "suggestions": SUGGESTIONS,
        "queries": {"q2": read_query_text("q2_explain_path"), "q5": read_query_text("q5_reopen_check")},
        "repo": os.getenv("PLUMBLINE_REPO_URL") or None,
    }
