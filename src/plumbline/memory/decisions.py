"""Decision memory: approve a verdict, store what it assumes, and reopen it when an assumption breaks.

``propose`` writes nothing. ``commit`` is the only writer of decisions and requires an approver, which is how a
human stays in the loop. ``reopen`` finds decisions whose assumptions were superseded (query Q5), marks them, and
re-evaluates them against current facts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from falkordb import Graph

from plumbline.graph.client import run_named
from plumbline.policy.verdict import POLICY_VERSION
from plumbline.triage.engine import ArtifactVerdict, triage_artifact
from plumbline.triage.receipt import make_receipt

ACTIONS = {"EXPOSED": "remediate", "CLEARED": "no_action", "UNKNOWN": "collect_evidence"}


@dataclass(frozen=True)
class Proposal:
    advisory: str
    artifact: str
    at_ms: int
    verdict: ArtifactVerdict

    @property
    def action(self) -> str:
        return ACTIONS[self.verdict.result.verdict]

    @property
    def decision_id(self) -> str:
        return f"dec:{self.advisory}:{self.artifact}@{self.at_ms}"


@dataclass(frozen=True)
class Reopened:
    decision: str
    advisory: str
    artifact: str
    before: str
    broken: tuple[str, ...]
    broken_ms: int
    now: ArtifactVerdict


def propose(graph: Graph, advisory: str, artifact: str, at_ms: int) -> Proposal:
    """Evaluate one (advisory, artifact) pair and describe the decision that would be recorded. Writes nothing."""
    verdict = triage_artifact(graph, advisory, artifact, at_ms)
    if verdict is None:
        raise LookupError(f"{advisory} is not published at the requested time, or {artifact} is unknown")
    return Proposal(advisory, artifact, at_ms, verdict)


def commit(graph: Graph, proposal: Proposal, approver: str) -> str:
    if not approver:
        raise ValueError("a decision needs an approver")
    r = proposal.verdict.result
    assumptions = [{"id": a.fact_id, "kind": a.kind, "key": a.key} for a in r.assumptions]
    run_named(graph, "memory/commit_decision", {
        "id": proposal.decision_id, "advisory": proposal.advisory, "artifact": proposal.artifact,
        "verdict": r.verdict, "reason": r.reason, "action": proposal.action, "at_ms": proposal.at_ms,
        "approver": approver, "policy_version": POLICY_VERSION, "assumptions": assumptions,
    }, read_only=False)
    receipt = make_receipt(proposal.advisory, proposal.at_ms, proposal.verdict)
    run_named(graph, "memory/commit_receipt", {
        "decision": proposal.decision_id, "hash": receipt["hash"],
        "payload": json.dumps(receipt["payload"], sort_keys=True),
    }, read_only=False)
    return proposal.decision_id


def reopen(graph: Graph, at_ms: int) -> list[Reopened]:
    """Mark every accepted decision with a superseded assumption as reopened and re-evaluate it."""
    out = []
    for decision, before, advisory, artifact, broken, broken_ms in run_named(
            graph, "q5_reopen_check", {"at_ms": at_ms}).result_set:
        run_named(graph, "memory/mark_reopened", {"id": decision, "at_ms": broken_ms}, read_only=False)
        now = triage_artifact(graph, advisory, artifact, max(at_ms, broken_ms))
        out.append(Reopened(decision, advisory, artifact, before, tuple(sorted(broken)), broken_ms, now))
    return out


def list_decisions(graph: Graph) -> list[dict]:
    header = ("decision", "verdict", "action", "status", "created_ms", "approver", "advisory", "artifact",
              "assumption_ids")
    return [dict(zip(header, row)) for row in run_named(graph, "memory/list_decisions").result_set]
