"""Per-upload graphs: isolation, limits, expiry and the HTTP surface (skipped without FalkorDB)."""

import concurrent.futures
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from plumbline import config, tenants
from plumbline.api.app import create_app
from plumbline.graph.client import connect

GATEWAY = (config.FIXTURES / "planted" / "gateway" / "package-lock.json").read_bytes()
ORDERS = (config.FIXTURES / "planted" / "orders-api" / "package-lock.json").read_bytes()
CLEAN = json.dumps({"lockfileVersion": 3, "packages": {
    "": {"dependencies": {"pino": "^9"}}, "node_modules/pino": {"version": "9.5.0"}}}).encode()


@pytest.fixture(autouse=True)
def database():
    try:
        g = connect()
        n = g.ro_query("MATCH (a:Artifact) RETURN count(a)").result_set[0][0]
    except Exception as exc:
        pytest.skip(f"FalkorDB not available: {exc}")
    if not n:
        pytest.skip("graph is empty; run `python -m plumbline load`")
    yield
    for name in tenants._tenant_names():
        connect(name).delete()


def verdicts(report):
    return {f["package"]: f["verdict"] for f in report["findings"]}


def test_an_upload_gets_a_report_with_paths_and_what_to_bump():
    r = tenants.create(GATEWAY, "my service")
    assert r["summary"] == {"EXPOSED": 3, "CLEARED": 3, "UNKNOWN": 0}
    keyv = next(f for f in r["findings"] if f["package"] == "keyv")
    assert keyv["verdict"] == "EXPOSED" and keyv["path"][-1] == "keyv@6.0.0" and keyv["pulled_by"] == ["@acme/http-client@1.4.0"]
    assert r["label"] == "my service" and r["expires"] > r["created"]


def test_a_clean_lockfile_is_cleared_with_stated_assumptions():
    r = tenants.create(CLEAN)
    assert set(verdicts(r).values()) == {"CLEARED"}
    assert all(f["assumptions"] for f in r["findings"])


def test_two_uploads_never_see_each_other_and_the_fleet_graph_is_untouched():
    before = connect().ro_query("MATCH (a:Artifact) RETURN count(a)").result_set[0][0]
    a, b = tenants.create(GATEWAY), tenants.create(CLEAN)
    assert verdicts(tenants.report(a["tenant"]))["keyv"] == "EXPOSED"
    assert verdicts(tenants.report(b["tenant"]))["keyv"] == "CLEARED"
    assert len(tenants.graph_payload(a["tenant"])["nodes"]) == 5 and len(tenants.graph_payload(b["tenant"])["nodes"]) == 1
    names = {n[1] for n in tenants.graph_payload(b["tenant"])["nodes"]}
    assert names == {"pino"}  # nothing from the other tenant, and nothing from the fleet
    assert connect().ro_query("MATCH (a:Artifact) RETURN count(a)").result_set[0][0] == before


def test_each_upload_is_its_own_graph_created_from_the_template():
    a, b = tenants.create(GATEWAY), tenants.create(ORDERS)
    names = tenants._tenant_names()
    assert f"{tenants.PREFIX}{a['tenant']}" in names and f"{tenants.PREFIX}{b['tenant']}" in names
    assert tenants.TEMPLATE not in names  # the template is not a tenant


def test_deleting_a_check_removes_its_graph():
    t = tenants.create(CLEAN)["tenant"]
    tenants.delete(t)
    with pytest.raises(tenants.TenantError):
        tenants.report(t)


def test_old_checks_are_swept(monkeypatch):
    t = tenants.create(CLEAN)["tenant"]
    monkeypatch.setattr(tenants, "TTL_MS", -1)
    assert tenants.sweep() >= 1
    with pytest.raises(tenants.TenantError):
        tenants.report(t)


@pytest.mark.parametrize("raw,why", [
    (b"not json", "valid JSON"),
    (json.dumps({"lockfileVersion": 1, "dependencies": {}}).encode(), "npm lockfiles"),
    (json.dumps({"lockfileVersion": 3, "packages": {"": {}}}).encode(), "no packages"),
    (b"[1, 2, 3]", "npm lockfile"),
    pytest.param(b"x" * (tenants.MAX_BYTES + 1), "larger", id="oversize"),
])
def test_unusable_uploads_are_rejected_with_a_reason(raw, why):
    with pytest.raises(tenants.TenantError, match=why):
        tenants.create(raw)


def test_tenant_ids_cannot_be_used_to_reach_other_graphs():
    for bad in ("plumbline", "../x", "efff2a6", "ZZZZZZZZ", "abcdef123"):
        with pytest.raises(tenants.TenantError):
            tenants.report(bad)


def test_concurrent_uploads_stay_separate():
    with concurrent.futures.ThreadPoolExecutor(6) as pool:
        results = list(pool.map(lambda raw: tenants.create(raw), [GATEWAY, CLEAN, ORDERS, CLEAN, GATEWAY, CLEAN]))
    ids = [r["tenant"] for r in results]
    assert len(set(ids)) == 6
    assert [r["summary"]["EXPOSED"] for r in results] == [3, 0, 1, 0, 3, 0]


def test_http_roundtrip_and_errors():
    client = TestClient(create_app())
    ok = client.post("/api/check", json={"lockfile": GATEWAY.decode(), "label": "http test"})
    assert ok.status_code == 200 and ok.json()["summary"]["EXPOSED"] == 3
    tid = ok.json()["tenant"]
    assert client.get(f"/api/check/{tid}").json()["label"] == "http test"
    assert len(client.get(f"/api/check/{tid}/graph").json()["nodes"]) == 5
    assert client.delete(f"/api/check/{tid}").json() == {"deleted": True}
    assert client.get(f"/api/check/{tid}").status_code == 404
    assert client.post("/api/check", json={"lockfile": "not json"}).status_code == 422
    assert client.get("/api/check/not-an-id").status_code == 404


def test_the_label_cannot_smuggle_markup():
    r = tenants.create(CLEAN, "<script>alert(1)</script> x")
    assert "<" not in r["label"] and ">" not in r["label"]


def test_template_file_does_not_exist_on_disk():
    assert not Path(config.DATA / "tenants").exists()


SAMPLES = config.ROOT / "web" / "samples"


@pytest.mark.parametrize("name,exposed,path_tail", [
    ("exposed-hand-authored.json", 3, ["@cacheable/utils@2.5.1", "keyv@6.0.0"]),
    ("exposed-real-nodemailer-edited.json", 1, ["flat-cache@4.0.1", "keyv@6.0.0"]),
    ("clear-real-nodemailer.json", 0, None),
])
def test_the_samples_offered_on_the_check_page_give_the_stated_verdicts(name, exposed, path_tail):
    r = tenants.create((SAMPLES / name).read_bytes())
    assert r["summary"]["EXPOSED"] == exposed and r["summary"]["UNKNOWN"] == 0
    if path_tail:
        assert next(f for f in r["findings"] if f["package"] == "keyv")["path"][-2:] == path_tail


def test_a_safe_keyv_is_cleared_even_though_the_package_name_matches():
    r = tenants.create((SAMPLES / "clear-real-nodemailer.json").read_bytes())
    keyv = next(f for f in r["findings"] if f["package"] == "keyv")
    assert keyv["verdict"] == "CLEARED" and [f"{e['name']}@{e['version']}" for e in keyv["evidence"]] == ["keyv@4.5.4"]


def test_the_report_carries_the_graph_queries_that_ran():
    r = tenants.create(GATEWAY)
    assert [q["name"] for q in r["work"]["queries"]] == ["relevant_locks", "q2_explain_path", "via_direct"]
    assert all("MATCH" in q["cypher"] for q in r["work"]["queries"])
    assert r["work"]["graph"]["installs"] == 5 and r["work"]["graph"]["requirements"] == 3
