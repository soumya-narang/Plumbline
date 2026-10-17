"""Visitors share one graph but never each other's approvals, and no visitor can wear the demo out."""

import pytest
from fastapi.testclient import TestClient

from plumbline.api import app as app_module
from plumbline.api.sessions import Approvals, Refused, clean_name
from plumbline.graph.client import connect

ADVISORY, ARTIFACT, AT = "MAL-2026-11524", "planted/gateway", "2026-08-04T12:00:00Z"


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    try:
        n = connect().ro_query("MATCH (a:Artifact) RETURN count(a)").result_set[0][0]
    except Exception as exc:
        pytest.skip(f"FalkorDB not available: {exc}")
    if not n:
        pytest.skip("graph is empty")
    monkeypatch.setattr(app_module, "approvals", Approvals())
    app_module._cache.clear()


def visitor() -> TestClient:
    return TestClient(app_module.create_app(), raise_server_exceptions=False)  # its own cookie jar


def approve(c, name="Ada"):
    return c.post("/api/approve", json={"advisory": ADVISORY, "artifact": ARTIFACT, "at": AT, "approver": name})


def approvers(c):
    return {d["approver"] for d in c.get("/api/snapshot", params={"at": AT}).json()["decisions"]}


def test_a_visitors_approval_is_theirs_alone():
    a, b = visitor(), visitor()
    assert approve(a, "Ada").status_code == 200
    assert "Ada" in approvers(a)
    assert "Ada" not in approvers(b)


def test_each_visitor_keeps_their_own_view_when_they_alternate():
    a, b = visitor(), visitor()
    approve(a, "Ada")
    approve(b, "Bo")
    for _ in range(2):
        assert "Ada" in approvers(a) and "Bo" not in approvers(a)
        assert "Bo" in approvers(b) and "Ada" not in approvers(b)


def test_the_session_cookie_is_http_only_and_not_guessable():
    c = visitor()
    r = c.get("/api/snapshot", params={"at": AT})
    cookie = r.headers["set-cookie"]
    assert "plumbline_session=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert len(c.cookies["plumbline_session"]) == 32


def test_a_forged_session_cookie_is_replaced_not_trusted():
    c = visitor()
    r = c.get("/api/snapshot", params={"at": AT}, headers={"cookie": "plumbline_session=../../etc/passwd"})
    issued = r.headers["set-cookie"].split("plumbline_session=")[1].split(";")[0]
    assert r.status_code == 200 and len(issued) == 32 and issued != "../../etc/passwd"


def test_approvals_are_rate_limited_per_address(monkeypatch):
    monkeypatch.setattr(app_module, "approvals", Approvals(per_hour=2))
    c = visitor()
    assert [approve(c).status_code for _ in range(3)] == [200, 200, 429]
    assert "per hour" in approve(c).json()["detail"]


def test_one_session_cannot_pile_up_approvals(monkeypatch):
    monkeypatch.setattr(app_module, "approvals", Approvals(max_per_session=1, per_hour=50))
    c = visitor()
    assert approve(c).status_code == 200
    r = approve(c)
    assert r.status_code == 429 and "at most 1 approvals" in r.json()["detail"]


def test_approvals_can_be_switched_off_for_a_read_only_deployment(monkeypatch):
    monkeypatch.setattr(app_module, "approvals", Approvals(enabled=False))
    r = approve(visitor())
    assert r.status_code == 403 and "switched off" in r.json()["detail"]
    assert visitor().get("/api/snapshot", params={"at": AT}).status_code == 200  # reading still works


def test_the_approver_name_is_cleaned_and_required():
    c = visitor()
    assert approve(c, "   \x00\x07  ").status_code == 422
    assert approve(c, "Ada\nLovelace\t\x1b[31m").status_code == 200
    assert "Ada Lovelace [31m" in approvers(c)


@pytest.mark.parametrize("raw,expected", [("  a   b ", "a b"), ("x" * 200, "x" * 80), ("tab\there", "tab here")])
def test_clean_name(raw, expected):
    assert clean_name(raw) == expected


def test_clean_name_refuses_blank_names():
    with pytest.raises(Refused):
        clean_name("\n\t ")


def test_old_sessions_are_forgotten_rather_than_growing_forever():
    store = Approvals(max_sessions=3)
    for i in range(5):
        store.add(f"s{i}", "client", {"n": i})
    assert [store.history(f"s{i}") != [] for i in range(5)] == [False, False, True, True, True]


def test_the_snapshot_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(app_module, "CACHE_LIMIT", 3)
    c = visitor()
    for hour in range(8, 14):
        c.get("/api/snapshot", params={"at": f"2026-08-04T{hour:02d}:00:00Z"})
    assert len(app_module._cache) <= 3
