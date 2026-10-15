"""Integration tests against a running FalkorDB with the fleet loaded (`python -m plumbline load`).

Skipped automatically when the database is unreachable or empty.
"""

import pytest

from plumbline.graph.client import connect, run_named


@pytest.fixture(scope="module")
def graph():
    try:
        g = connect()
        loaded = g.ro_query("MATCH (a:Artifact) RETURN count(a)").result_set[0][0]
    except Exception as exc:  # connection refused, graph missing
        pytest.skip(f"FalkorDB not available: {exc}")
    if not loaded:
        pytest.skip("graph is empty; run `python -m plumbline load`")
    return g


def test_only_planted_artifacts_lock_a_malicious_version(graph):
    rows = run_named(graph, "q1_exposure_base").result_set
    assert {r[2] for r in rows} == {"planted/orders-api", "planted/gateway"}
    assert {r[0] for r in rows} == {"MAL-2026-11523", "MAL-2026-11524", "MAL-2026-11559", "MAL-2026-11561"}


def test_explain_path_follows_the_dependency_chain(graph):
    chain, hops = run_named(
        graph, "q2_explain_path", {"artifact": "planted/gateway", "purl": "pkg:npm/keyv@6.0.0"}
    ).result_set[0]
    assert hops == 3
    assert chain == ["@acme/http-client@1.4.0", "@cacheable/net@2.1.1", "@cacheable/utils@2.5.1", "keyv@6.0.0"]


def test_direct_dependency_has_a_zero_length_path(graph):
    _, hops = run_named(
        graph, "q2_explain_path", {"artifact": "planted/orders-api", "purl": "pkg:npm/cache-manager@7.2.10"}
    ).result_set[0]
    assert hops == 0


def test_no_path_returns_no_rows(graph):
    rows = run_named(
        graph, "q2_explain_path", {"artifact": "planted/orders-api", "purl": "pkg:npm/keyv@6.0.0"}
    ).result_set
    assert rows == []


def test_near_miss_is_visible_in_the_graph(graph):
    rows = graph.ro_query(
        "MATCH (:Artifact {id:'nestjs/nest'})-[:LOCKS]->(:LockedDep)-[:IS]->(pv:PackageVersion {name:'cache-manager'}) "
        "RETURN pv.version"
    ).result_set
    assert rows == [["7.2.9"]]  # one patch below the malicious 7.2.10


def test_every_package_version_node_has_a_name_and_version(graph):
    nameless = graph.ro_query(
        "MATCH (pv:PackageVersion) WHERE pv.name IS NULL OR pv.version IS NULL RETURN pv.purl").result_set
    assert nameless == []
