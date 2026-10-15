"""Graph-backed triage: gather evidence with Cypher, then let the policy decide.

The graph supplies facts (what each artifact locks, what an advisory names, the path between them). The verdict
itself always comes from ``plumbline.policy.verdict.evaluate``.
"""

from __future__ import annotations

from dataclasses import dataclass

from falkordb import Graph

from plumbline.graph.client import run_named
from plumbline.policy.verdict import AdvisoryState, ArtifactState, Locked, Result, evaluate

_ORDER = {"EXPOSED": 0, "UNKNOWN": 1, "CLEARED": 2}


@dataclass(frozen=True)
class ArtifactVerdict:
    artifact: str
    kind: str
    service: str | None
    tier: int | None
    exposure: str | None
    lock_sha256: str | None
    result: Result
    path: tuple[str, ...] | None  # shortest chain from a direct dependency to the affected package
    hops: int | None
    path_keys: tuple[str, ...] | None = None  # the same chain as lockfile keys, to light it up in the graph view
    pulled_by: tuple[str, ...] = ()  # direct dependencies that pull an affected version in: what to bump


@dataclass(frozen=True)
class TriageReport:
    advisory: AdvisoryState
    at_ms: int
    verdicts: tuple[ArtifactVerdict, ...]

    def counts(self) -> dict[str, int]:
        out = {"EXPOSED": 0, "CLEARED": 0, "UNKNOWN": 0}
        for v in self.verdicts:
            out[v.result.verdict] += 1
        return out


def load_advisory(graph: Graph, advisory_id: str, at_ms: int) -> AdvisoryState | None:
    rows = run_named(graph, "triage/advisory_at", {"advisory": advisory_id, "at_ms": at_ms}).result_set
    if not rows:
        return None
    _, package, _, purls = rows[0]
    return AdvisoryState(advisory_id, package, frozenset(purls))


def _locked_by_artifact(graph: Graph, advisory: AdvisoryState) -> dict[str, tuple[Locked, ...]]:
    rows = run_named(graph, "triage/relevant_locks",
                     {"package": advisory.package, "purls": sorted(advisory.affected_purls)}).result_set
    best: dict[tuple[str, str], Locked] = {}
    for artifact, purl, name, version, depth, dev in rows:
        key = (artifact, purl)
        cand = Locked(purl, name, version, depth, bool(dev))
        # The same version can be locked at several depths; keep the shallowest.
        if key not in best or (cand.depth or 99) < (best[key].depth or 99):
            best[key] = cand
    out: dict[str, list[Locked]] = {}
    for (artifact, _), locked in best.items():
        out.setdefault(artifact, []).append(locked)
    return {a: tuple(v) for a, v in out.items()}


def _shortest_path(graph: Graph, artifact: str, hits: tuple[Locked, ...]):
    best: tuple[tuple[str, ...], int, tuple[str, ...]] | None = None
    for hit in hits:
        rows = run_named(graph, "q2_explain_path", {"artifact": artifact, "purl": hit.purl}).result_set
        if rows and (best is None or rows[0][1] < best[1]):
            best = (tuple(rows[0][0]), rows[0][1], tuple(rows[0][2]))
    return best if best else (None, None, None)


def _pulled_by(graph: Graph, artifact: str, hits: tuple[Locked, ...]) -> tuple[str, ...]:
    names: set[str] = set()
    for hit in hits:
        for name, version in run_named(graph, "triage/via_direct", {"artifact": artifact, "purl": hit.purl}).result_set:
            names.add(f"{name}@{version}")
    return tuple(sorted(names))


def triage_advisory(graph: Graph, advisory_id: str, at_ms: int) -> TriageReport | None:
    """Evaluate every artifact against one advisory as known at ``at_ms``; ``None`` if it is not yet published."""
    advisory = load_advisory(graph, advisory_id, at_ms)
    if advisory is None:
        return None
    locks = _locked_by_artifact(graph, advisory)
    verdicts = []
    for artifact, kind, lock_state, lock_sha, service, tier, exposure in run_named(graph, "triage/artifacts").result_set:
        state = ArtifactState(artifact, lock_state, lock_sha, locks.get(artifact, ()))
        result = evaluate(state, advisory)
        exposed = result.verdict == "EXPOSED"
        path, hops, keys = _shortest_path(graph, artifact, result.evidence) if exposed else (None, None, None)
        pulled = _pulled_by(graph, artifact, result.evidence) if exposed else ()
        verdicts.append(ArtifactVerdict(artifact, kind, service, tier, exposure, lock_sha, result, path, hops, keys, pulled))
    verdicts.sort(key=lambda v: (
        _ORDER[v.result.verdict],
        0 if v.exposure == "internet" else 1,  # priority orders EXPOSED rows; it never changes a verdict
        v.tier or 9,
        v.artifact,
    ))
    return TriageReport(advisory, at_ms, tuple(verdicts))


def triage_artifact(graph: Graph, advisory_id: str, artifact_id: str, at_ms: int) -> ArtifactVerdict | None:
    report = triage_advisory(graph, advisory_id, at_ms)
    if report is None:
        return None
    return next((v for v in report.verdicts if v.artifact == artifact_id), None)
