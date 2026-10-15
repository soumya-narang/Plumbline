"""Integration tests for triage and receipts against the loaded fleet (skipped without FalkorDB)."""

import copy

import pytest

from plumbline.graph.client import connect
from plumbline.timeutil import to_ms
from plumbline.triage.engine import triage_advisory
from plumbline.triage.receipt import make_receipt, payload_hash, verify

T = to_ms("2026-08-04T11:40:00Z")  # after all six advisories are published


@pytest.fixture(scope="module")
def graph():
    try:
        g = connect()
        n = g.ro_query("MATCH (a:Artifact) RETURN count(a)").result_set[0][0]
    except Exception as exc:
        pytest.skip(f"FalkorDB not available: {exc}")
    if not n:
        pytest.skip("graph is empty; run `python -m plumbline load`")
    return g


def by_artifact(report):
    return {v.artifact: v for v in report.verdicts}


def test_not_visible_before_publication(graph):
    assert triage_advisory(graph, "MAL-2026-11524", to_ms("2026-08-04T11:00:00Z")) is None


def test_exactly_one_artifact_is_exposed_per_advisory(graph):
    expected = {"MAL-2026-11523": {"planted/orders-api"}, "MAL-2026-11524": {"planted/gateway", "planted/storefront"}}
    for adv, artifacts in expected.items():
        exposed = {v.artifact for v in triage_advisory(graph, adv, T).verdicts if v.result.verdict == "EXPOSED"}
        assert exposed == artifacts


def test_missing_lockfiles_are_unknown_not_cleared(graph):
    v = by_artifact(triage_advisory(graph, "MAL-2026-11524", T))
    assert v["eslint/eslint"].result.verdict == "UNKNOWN"
    assert v["sindresorhus/got"].result.reason == "no_lockfile"
    assert v["typeorm/typeorm"].result.reason == "lockfile_format_unsupported"


def test_near_miss_is_cleared_with_its_safe_version_cited(graph):
    nest = by_artifact(triage_advisory(graph, "MAL-2026-11523", T))["nestjs/nest"]
    assert nest.result.verdict == "CLEARED"
    assert [x.version for x in nest.result.evidence] == ["7.2.9"]


def test_exposed_verdict_carries_the_dependency_path(graph):
    gw = by_artifact(triage_advisory(graph, "MAL-2026-11524", T))["planted/gateway"]
    assert gw.hops == 3 and gw.path[0].startswith("@acme/http-client") and gw.path[-1] == "keyv@6.0.0"


def test_receipt_verifies_and_is_stable(graph):
    v = by_artifact(triage_advisory(graph, "MAL-2026-11524", T))["planted/gateway"]
    receipt = make_receipt("MAL-2026-11524", T, v)
    assert verify(graph, receipt)[0] is True
    assert make_receipt("MAL-2026-11524", T, v)["hash"] == receipt["hash"]


def test_altering_a_receipt_payload_is_detected(graph):
    v = by_artifact(triage_advisory(graph, "MAL-2026-11524", T))["planted/gateway"]
    receipt = make_receipt("MAL-2026-11524", T, v)
    forged = copy.deepcopy(receipt)
    forged["payload"]["verdict"] = "CLEARED"
    ok, why = verify(graph, forged)
    assert ok is False and "altered" in why


def test_a_forged_receipt_with_a_recomputed_hash_is_still_rejected(graph):
    v = by_artifact(triage_advisory(graph, "MAL-2026-11524", T))["planted/gateway"]
    forged_payload = {**make_receipt("MAL-2026-11524", T, v)["payload"], "verdict": "CLEARED"}
    ok, why = verify(graph, {"payload": forged_payload, "hash": payload_hash(forged_payload)})
    assert ok is False and "verdict" in why
