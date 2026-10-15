import pytest
from fastapi.testclient import TestClient

from plumbline.api.app import _cache, _manual, create_app
from plumbline.graph.client import connect
from plumbline.memory.replay import reset

BEFORE = "2026-08-04T12:00:00Z"
AFTER = "2026-08-04T13:00:00Z"


@pytest.fixture()
def client():
    try:
        g = connect()
        n = g.ro_query("MATCH (a:Artifact) RETURN count(a)").result_set[0][0]
    except Exception as exc:
        pytest.skip(f"FalkorDB not available: {exc}")
    if not n:
        pytest.skip("graph is empty; run `python -m plumbline load`")
    _cache.clear()
    _manual.clear()
    reset(g)
    yield TestClient(create_app())
    _cache.clear()
    _manual.clear()
    reset(g)


def test_health(client):
    assert client.get("/api/health").json()["ok"] is True


def test_meta_has_a_labelled_timeline_and_agent_mode(client):
    meta = client.get("/api/meta").json()
    assert meta["mode"] == "live" and len(meta["timeline"]) == 13
    assert [s for s in meta["timeline"] if s["scripted"]][0]["kind"] == "revision"
    assert meta["agent"]["backend"] in ("planner", "llm")


def test_snapshot_before_and_after_the_revision(client):
    before = client.get("/api/snapshot", params={"at": BEFORE}).json()
    after = client.get("/api/snapshot", params={"at": AFTER}).json()
    assert before["reopened"] == []
    assert [r["artifact"] for r in after["reopened"]] == ["planted/billing-worker"]


def test_snapshot_cache_does_not_serve_stale_memory(client):
    first = client.get("/api/snapshot", params={"at": AFTER}).json()
    client.get("/api/snapshot", params={"at": BEFORE})  # moves the graph back
    again = client.get("/api/snapshot", params={"at": AFTER}).json()
    assert first == again


def test_bad_timestamp_is_rejected(client):
    assert client.get("/api/snapshot", params={"at": "not-a-time"}).status_code == 422


def test_ask_uses_the_planner_and_returns_its_tool_trace(client):
    r = client.post("/api/ask", json={"question": "Why is the edge gateway exposed?", "at": BEFORE}).json()
    assert r["backend"] in ("planner", "llm")
    assert [c["name"] for c in r["calls"]][:2] == ["list_advisories", "triage_advisory"]


def test_approving_writes_a_decision_with_a_human_approver(client):
    r = client.post("/api/approve", json={"advisory": "MAL-2026-11524", "artifact": "planted/gateway",
                                          "at": BEFORE, "approver": "alex"})
    assert r.status_code == 200
    ids = [d["decision"] for d in r.json()["snapshot"]["decisions"]]
    assert r.json()["decision"] in ids


def test_approval_requires_an_approver(client):
    r = client.post("/api/approve", json={"advisory": "MAL-2026-11524", "artifact": "planted/gateway",
                                          "at": BEFORE, "approver": ""})
    assert r.status_code == 422


def test_receipt_roundtrip_and_tamper_detection(client):
    receipt = client.get("/api/receipt", params={"advisory": "MAL-2026-11524", "artifact": "planted/gateway",
                                                 "at": BEFORE}).json()
    assert client.post("/api/verify", json=receipt).json()["ok"] is True
    receipt["payload"]["verdict"] = "CLEARED"
    bad = client.post("/api/verify", json=receipt).json()
    assert bad["ok"] is False and "altered" in bad["detail"]


def test_a_manual_approval_survives_moving_the_timeline_but_not_travelling_before_it(client):
    body = {"advisory": "MAL-2026-11524", "artifact": "planted/gateway", "at": "2026-08-04T12:10:00Z", "approver": "alex"}
    decision = client.post("/api/approve", json=body).json()["decision"]

    def ids(at):
        return [d["decision"] for d in client.get("/api/snapshot", params={"at": at}).json()["decisions"]]

    assert decision in ids("2026-08-04T13:00:00Z")      # later: still there
    assert decision not in ids("2026-08-04T12:00:00Z")  # earlier: it had not happened yet


def test_manual_approval_records_who_approved(client):
    body = {"advisory": "MAL-2026-11524", "artifact": "planted/gateway", "at": BEFORE, "approver": "alex"}
    snap = client.post("/api/approve", json=body).json()["snapshot"]
    manual = [e for e in snap["events"] if e["manual"]]
    assert manual and manual[0]["approver"] == "alex"
