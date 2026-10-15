"""The graph-native features: fleet-wide fix-first, PageRank, the path's lockfile keys and the graph payload."""

import pytest
from fastapi.testclient import TestClient

from plumbline.agent.tools import critical_dependencies, fix_first
from plumbline.api.app import create_app
from plumbline.graph.client import connect
from plumbline.graphdata import artifact_graph
from plumbline.memory.replay import reset
from plumbline.timeutil import to_ms
from plumbline.triage.engine import triage_artifact

T = "2026-08-04T11:40:00Z"


@pytest.fixture(scope="module")
def graph():
    try:
        g = connect()
        n = g.ro_query("MATCH (a:Artifact) RETURN count(a)").result_set[0][0]
    except Exception as exc:
        pytest.skip(f"FalkorDB not available: {exc}")
    if not n:
        pytest.skip("graph is empty; run `python -m plumbline load`")
    reset(g)
    return g


def test_fix_first_names_the_direct_dependency_that_pulls_the_version_in(graph):
    bump = {b["package"]: b for b in fix_first("MAL-2026-11524", T)["bump"]}
    assert bump["@acme/http-client@1.4.0"]["in_artifacts"] == ["planted/gateway"]
    assert bump["@acme/payments-sdk@2.1.0"]["in_artifacts"] == ["planted/storefront"]


def test_fix_first_is_empty_when_nothing_is_exposed_yet(graph):
    assert fix_first("MAL-2026-11524", "2026-08-04T11:00:00Z")["bump"] == []


def test_each_exposed_verdict_says_what_to_bump(graph):
    v = triage_artifact(graph, "MAL-2026-11524", "planted/storefront", to_ms(T))
    assert v.pulled_by == ("@acme/payments-sdk@2.1.0",)
    assert v.path_keys[0] == "node_modules/@acme/payments-sdk" and v.path_keys[-1].endswith("/keyv")


def test_critical_dependencies_ranks_by_pagerank_within_one_artifact(graph):
    out = critical_dependencies("planted/storefront", 5)
    scores = [p["score"] for p in out["packages"]]
    assert len(scores) == 5 and scores == sorted(scores, reverse=True)
    assert out["ranked_by"] == "PageRank over REQUIRES"


def test_critical_dependencies_stays_inside_the_requested_artifact(graph):
    names = {p["package"] for p in critical_dependencies("planted/gateway", 25)["packages"]}
    assert names <= {"@acme/http-client@1.4.0", "@cacheable/net@2.1.1", "@cacheable/utils@2.5.1", "keyv@6.0.0", "pino@9.5.0"}


def test_graph_payload_is_compact_and_indexes_its_own_nodes(graph):
    data = artifact_graph(graph, "planted/storefront")
    assert len(data["nodes"]) == 686 and data["edges"]
    assert all(0 <= s < len(data["nodes"]) and 0 <= t < len(data["nodes"]) for s, t in data["edges"])
    assert any(n[0].endswith("/keyv") and n[2] == "6.0.0" for n in data["nodes"])


def test_graph_endpoint_serves_the_payload_and_rejects_unknown_artifacts(graph):
    client = TestClient(create_app())
    assert client.get("/api/graph", params={"artifact": "planted/gateway"}).json()["nodes"]
    assert client.get("/api/graph", params={"artifact": "sindresorhus/got"}).status_code == 404
