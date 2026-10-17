"""A shared work queue between agents, kept in the graph.

A triage agent finds exposures and hands each fix over as a ``Task``; remediation agents claim, work and complete
them. The graph is the only thing the agents share. Every state change is a single Cypher write, and FalkorDB runs
write queries on a graph one at a time, so concurrent agents cannot claim the same task or complete each other's.

When a task is completed, the resolution is remembered as a ``Playbook`` for that package (procedural memory), and
the next hand-off for the same package carries it as a suggestion.

Tasks sit beside the decision memory, not inside it: replaying the incident rewrites decisions, never tasks.
"""

from __future__ import annotations

import threading

from falkordb import Graph
from redis.exceptions import ResponseError

from plumbline.graph.client import run_named
from plumbline.timeutil import now_ms, to_iso
from plumbline.triage.engine import triage_artifact

MAX_OPEN = 50
MAX_TEXT = 300

_schema_lock = threading.Lock()
_schema_ready: set[str] = set()


class WorkError(ValueError):
    """The request cannot be honoured; the message is safe to show to an agent or a person."""


def ensure_schema(graph: Graph) -> None:
    """Index the task and playbook ids, and register the properties, once per graph.

    Registering the properties up front matters: FalkorDB can fail on a query that returns a property no node has had.
    """
    with _schema_lock:
        if graph.name in _schema_ready:
            return
        for label, prop in (("Task", "id"), ("Task", "status"), ("Playbook", "id")):
            try:
                graph.create_node_range_index(label, prop)
            except ResponseError as exc:
                if "already indexed" not in str(exc).lower():
                    raise
        try:
            graph.create_node_unique_constraint("Task", "id")
            graph.create_node_unique_constraint("Playbook", "id")
        except ResponseError as exc:
            if "already" not in str(exc).lower():
                raise
        _schema_ready.add(graph.name)


def _text(value: str, what: str) -> str:
    value = " ".join(value.split())[:MAX_TEXT]
    if not value:
        raise WorkError(f"{what} is required")
    return value


def _who(agent: str) -> str:
    return _text(agent, "an agent name")[:60]


def task_id(advisory: str, artifact: str) -> str:
    return f"task:{advisory}:{artifact}"


def playbook_id(package: str) -> str:
    return f"bump:{package}"


def hand_off(graph: Graph, advisory: str, artifact: str, at_ms: int, by: str, note: str = "") -> dict:
    """Create the remediation task for an exposed artifact. The fix comes from the graph, never from the caller."""
    ensure_schema(graph)
    by = _who(by)
    verdict = triage_artifact(graph, advisory, artifact, at_ms)
    if verdict is None:
        raise WorkError(f"no verdict for {artifact} against {advisory} at that time")
    if verdict.result.verdict != "EXPOSED":
        raise WorkError(f"{artifact} is {verdict.result.verdict} for {advisory}; only an EXPOSED artifact needs a fix")
    if run_named(graph, "work/count_open").result_set[0][0] >= MAX_OPEN:
        raise WorkError(f"the queue already holds {MAX_OPEN} unfinished tasks")
    # The queue is shared. A what-if (or the scripted revision) is only a story about the advisory, so it must never put
    # work in front of other agents or people: only versions the advisory names as published count, and the path and the
    # fix are taken from those alone.
    real = [r[0] for r in run_named(graph, "work/real_purls", {
        "advisory": advisory, "purls": [e.purl for e in verdict.result.evidence]}).result_set]
    if not real:
        raise WorkError(f"{artifact} is exposed only if a hypothetical advisory revision were real, so no task was created")
    chains, bumps = [], set()
    for purl in real:
        found = run_named(graph, "q2_explain_path", {"artifact": artifact, "purl": purl}).result_set
        if found:
            chains.append(found[0][0])
        bumps |= {f"{name}@{version}" for name, version in run_named(graph, "triage/via_direct", {"artifact": artifact, "purl": purl}).result_set}
    path = min(chains, key=len) if chains else list(verdict.path or ())
    fix = ", ".join(sorted(bumps)) or "upgrade the affected package"
    rows = run_named(graph, "work/create_task", {
        "id": task_id(advisory, artifact), "advisory": advisory, "artifact": artifact, "fix": fix,
        "note": " ".join(note.split())[:MAX_TEXT], "by": by, "now_ms": now_ms()}, read_only=False).result_set
    if not rows:
        raise WorkError(f"{advisory} or {artifact} is not in the graph")
    tid, status, claimed_by, created = rows[0]
    package = _package_of(graph, advisory)
    recalled = run_named(graph, "work/find_playbook", {"playbook": playbook_id(package)}).result_set
    return {"task": tid, "status": status, "claimed_by": claimed_by or None, "created": bool(created),
            "fix": fix, "path": path,
            "recalled": {"resolution": recalled[0][0], "times_used": recalled[0][1]} if recalled else None}


def _package_of(graph: Graph, advisory: str) -> str:
    rows = run_named(graph, "triage/advisory_at", {"advisory": advisory, "at_ms": 2**62}).result_set
    return rows[0][1] if rows else advisory


def claim(graph: Graph, agent: str) -> dict:
    """Take the oldest open task, or report that none is waiting. Atomic across concurrent agents."""
    ensure_schema(graph)
    rows = run_named(graph, "work/claim_task", {"agent": _who(agent), "now_ms": now_ms()}, read_only=False).result_set
    if not rows:
        return {"task": None, "message": "no open tasks"}
    tid, advisory, artifact, fix, note = rows[0]
    return {"task": {"id": tid, "advisory": advisory, "artifact": artifact, "fix": fix, "note": note}}


def complete(graph: Graph, tid: str, agent: str, resolution: str) -> dict:
    """Finish a task claimed by this agent, and remember how it was resolved."""
    ensure_schema(graph)
    agent, resolution = _who(agent), _text(resolution, "a resolution")
    rows = run_named(graph, "work/complete_task", {"id": tid, "agent": agent, "resolution": resolution, "now_ms": now_ms()},
                     read_only=False).result_set
    if not rows:
        raise WorkError("that task is not claimed by this agent (it may be open, done, or someone else's)")
    _, advisory, _artifact = rows[0]
    package = _package_of(graph, advisory)
    uses = run_named(graph, "work/record_playbook", {
        "playbook": playbook_id(package), "package": package, "task": tid, "resolution": resolution, "now_ms": now_ms()},
        read_only=False).result_set[0][0]
    return {"task": tid, "status": "done", "playbook": playbook_id(package), "times_used": uses}


def list_tasks(graph: Graph, status: str = "") -> list[dict]:
    ensure_schema(graph)
    if status not in ("", "open", "claimed", "done"):
        raise WorkError("status must be open, claimed, done, or empty for all")
    out = []
    for (tid, st, advisory, artifact, fix, note, by, claimed_by, resolution, created, claimed, done) in \
            run_named(graph, "work/list_tasks", {"status": status}).result_set:
        out.append({"id": tid, "status": st, "advisory": advisory, "artifact": artifact, "fix": fix, "note": note or None,
                    "created_by": by, "claimed_by": claimed_by or None, "resolution": resolution or None,
                    "created": to_iso(created), "claimed": to_iso(claimed) if claimed else None,
                    "done": to_iso(done) if done else None})
    return out
