"""Integration tests for decision memory and the replay (skipped without a loaded FalkorDB).

The replay writes Decision and Fact nodes, so every test resets them afterwards.
"""

import pytest

from plumbline.graph.client import connect
from plumbline.memory.decisions import commit, list_decisions, propose
from plumbline.memory.replay import reset, seek
from plumbline.timeutil import to_ms

BEFORE_REVISION = to_ms("2026-08-04T12:00:00Z")
AFTER_REVISION = to_ms("2026-08-04T13:00:00Z")


@pytest.fixture()
def graph():
    try:
        g = connect()
        n = g.ro_query("MATCH (a:Artifact) RETURN count(a)").result_set[0][0]
    except Exception as exc:
        pytest.skip(f"FalkorDB not available: {exc}")
    if not n:
        pytest.skip("graph is empty; run `python -m plumbline load`")
    reset(g)
    yield g
    reset(g)


def status(state):
    return {d["artifact"]: d["status"] for d in state.decisions}


def test_propose_writes_nothing(graph):
    propose(graph, "MAL-2026-11524", "planted/gateway", BEFORE_REVISION)
    assert list_decisions(graph) == []


def test_a_decision_needs_an_approver(graph):
    p = propose(graph, "MAL-2026-11524", "planted/gateway", BEFORE_REVISION)
    with pytest.raises(ValueError):
        commit(graph, p, approver="")


def test_nothing_reopens_before_the_revision(graph):
    state = seek(graph, BEFORE_REVISION)
    assert len(state.decisions) == 5
    assert set(status(state).values()) == {"accepted"}
    assert state.reopened == ()


def test_exactly_one_decision_reopens_after_the_revision(graph):
    state = seek(graph, AFTER_REVISION)
    assert [r.artifact for r in state.reopened] == ["planted/billing-worker"]
    assert [a for a, s in status(state).items() if s == "reopened"] == ["planted/billing-worker"]


def test_the_reopened_decision_names_the_exact_broken_assumption(graph):
    (r,) = seek(graph, AFTER_REVISION).reopened
    assert r.before == "CLEARED" and r.now.result.verdict == "EXPOSED"
    assert r.broken == ("not_affected:MAL-2026-11524:pkg:npm/keyv@6.0.1",)


def test_unrelated_cleared_decisions_stay_accepted(graph):
    s = status(seek(graph, AFTER_REVISION))
    assert s["mochajs/mocha"] == "accepted" and s["nestjs/nest"] == "accepted"


def test_exposed_decisions_depend_on_the_lockfile(graph):
    seek(graph, BEFORE_REVISION)
    rows = graph.ro_query(
        "MATCH (d:Decision {verdict:'EXPOSED'})-[:ASSUMES]->(f:Fact) RETURN f.kind, count(d)").result_set
    assert rows == [["lock_snapshot", 2]]


def test_seeking_is_idempotent_and_reversible(graph):
    first = seek(graph, AFTER_REVISION)
    again = seek(graph, AFTER_REVISION)
    assert status(first) == status(again)
    rewound = seek(graph, BEFORE_REVISION)
    assert set(status(rewound).values()) == {"accepted"}


def test_the_scripted_edge_does_not_leak_into_the_real_graph(graph):
    seek(graph, AFTER_REVISION)
    reset(graph)
    scripted = graph.ro_query("MATCH ()-[e:AFFECTS {scripted:true}]->() RETURN count(e)").result_set[0][0]
    assert scripted == 0


def test_decisions_list_their_assumption_ids_and_approver(graph):
    state = seek(graph, BEFORE_REVISION)
    billing = next(d for d in state.decisions if d["artifact"] == "planted/billing-worker")
    assert billing["approver"] == "replay"
    assert "not_affected:MAL-2026-11524:pkg:npm/keyv@6.0.1" in billing["assumption_ids"]
    assert any(a.startswith("lock_snapshot:") for a in billing["assumption_ids"])
