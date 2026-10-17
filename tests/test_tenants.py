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
    for bad in ("plumbline", "../x", "efff2a6", "ZZZZZZZZ", "abcdef123", "0123abcd", "g" * 32, "0" * 33):
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


def test_check_ids_are_long_enough_not_to_be_guessed():
    r = tenants.create(CLEAN)
    assert len(r["tenant"]) == 32 and int(r["tenant"], 16) >= 0


def test_one_client_cannot_hold_more_than_its_share():
    for _ in range(tenants.MAX_PER_OWNER):
        tenants.create(CLEAN, owner="alice")
    with pytest.raises(tenants.TenantError, match=r"already have 3 checks open; delete one or wait \d+ min"):
        tenants.create(CLEAN, owner="alice")
    assert tenants.create(CLEAN, owner="bob")["summary"]["EXPOSED"] == 0  # another client is unaffected


def test_deleting_a_check_frees_the_clients_slot():
    ids = [tenants.create(CLEAN, owner="carol")["tenant"] for _ in range(tenants.MAX_PER_OWNER)]
    tenants.delete(ids[0])
    assert tenants.create(CLEAN, owner="carol")["tenant"]


def test_the_global_cap_says_how_long_to_wait(monkeypatch):
    monkeypatch.setattr(tenants, "MAX_TENANTS", 2)
    monkeypatch.setattr(tenants, "MAX_PER_OWNER", 10)
    tenants.create(CLEAN, owner="a")
    tenants.create(CLEAN, owner="b")
    with pytest.raises(tenants.TenantError, match=r"try again in \d+ min"):
        tenants.create(CLEAN, owner="c")


def test_a_lockfile_with_an_absurd_number_of_links_is_refused_before_any_graph_work():
    n = 400
    pk = {"": {"dependencies": {f"p{i}": "1" for i in range(n)}}}
    for i in range(n):
        pk[f"node_modules/p{i}"] = {"version": "1.0.0", "dependencies": {f"p{(i * 7 + j) % n}": "1" for j in range(1, 80)}}
    before = len(tenants._tenant_names())
    with pytest.raises(tenants.TenantError, match="dependency links"):
        tenants.create(json.dumps({"lockfileVersion": 3, "packages": pk}).encode())
    assert len(tenants._tenant_names()) == before


def test_deeply_nested_json_is_a_clean_refusal_not_a_crash():
    with pytest.raises(tenants.TenantError, match="nested too deeply"):
        tenants.create(b"[" * 100_000 + b"]" * 100_000)
    resp = TestClient(create_app(), raise_server_exceptions=False).post("/api/check", json={"lockfile": "[" * 100_000 + "]" * 100_000})
    assert resp.status_code == 422 and "nested too deeply" in resp.json()["detail"]


def test_a_slow_upload_does_not_block_another_one(monkeypatch):
    import threading
    import time

    real = tenants.load_lockgraph_rows
    gate = threading.Event()
    calls = []

    def slow_first(graph, rows):
        calls.append(1)
        if len(calls) == 1:
            gate.wait(10)
        return real(graph, rows)

    monkeypatch.setattr(tenants, "load_lockgraph_rows", slow_first)
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        slow = pool.submit(tenants.create, CLEAN)
        while not calls:
            time.sleep(0.01)
        started = time.time()
        quick = pool.submit(tenants.create, CLEAN).result(timeout=8)
        assert time.time() - started < 5 and quick["tenant"]
        gate.set()
        assert slow.result(timeout=10)["tenant"] != quick["tenant"]


def test_a_graph_that_is_still_loading_is_not_swept(monkeypatch):
    tenants.ensure_template()
    tid = "f" * 32
    connect(tenants.TEMPLATE).copy(tenants.PREFIX + tid)
    tenants._loading[tid] = "x"
    try:
        monkeypatch.setattr(tenants, "TTL_MS", -1)
        tenants.sweep()
        assert tenants.PREFIX + tid in tenants._tenant_names()
    finally:
        tenants._loading.pop(tid, None)


def test_a_failed_load_leaves_no_graph_and_frees_the_slot(monkeypatch):
    def boom(graph, rows):
        raise RuntimeError("database went away")

    monkeypatch.setattr(tenants, "load_lockgraph_rows", boom)
    before = len(tenants._tenant_names())
    with pytest.raises(RuntimeError):
        tenants.create(CLEAN, owner="dave")
    assert len(tenants._tenant_names()) == before and not tenants._loading


def test_your_own_list_of_bad_versions_is_judged_like_the_incident():
    r = tenants.create((SAMPLES / "clear-real-nodemailer.json").read_bytes(), extra=["keyv@4.5.4"])
    mine = [f for f in r["findings"] if f["advisory"].startswith("YOUR-LIST")]
    assert len(r["findings"]) == 7 and len(mine) == 1 and mine[0]["verdict"] == "EXPOSED"
    assert mine[0]["path"] == ["eslint@10.8.0", "file-entry-cache@8.0.0", "flat-cache@4.0.1", "keyv@4.5.4"]
    assert mine[0]["pulled_by"] == ["eslint@10.8.0"]
    incident = next(f for f in r["findings"] if f["package"] == "keyv" and not f["advisory"].startswith("YOUR-LIST"))
    assert incident["verdict"] == "CLEARED"  # the incident's own verdict is unchanged by adding a list


def test_a_list_that_names_nothing_the_project_locks_clears_it():
    r = tenants.create(GATEWAY, extra=["left-pad@1.3.0", "@scope/none@2.0.0"])
    assert [f["verdict"] for f in r["findings"] if f["advisory"].startswith("YOUR-LIST")] == ["CLEARED", "CLEARED"]


def test_scoped_packages_and_several_versions_of_one_package_group_correctly():
    rows = tenants.parse_extra(["@cacheable/utils@2.5.1", "@cacheable/utils@2.5.0", "keyv@6.0.0", " keyv@6.0.0 ", ""])
    assert [(r["package"], [a["version"] for a in r["affected"]]) for r in rows] == [
        ("@cacheable/utils", ["2.5.0", "2.5.1"]), ("keyv", ["6.0.0"])]
    assert rows[0]["affected"][0]["purl"] == "pkg:npm/%40cacheable/utils@2.5.0"
    assert tenants.create(GATEWAY, extra=["@cacheable/utils@2.5.1"])["summary"]["EXPOSED"] == 4  # incident's 3, plus the listed one


@pytest.mark.parametrize("entry", ["keyv", "@6.0.0", "keyv@", "keyv@latest", "keyv@^6", "Keyv@6.0.0", "../x@1.0.0", "a b@1.0.0",
                                   "keyv@1.0.0'}) DETACH DELETE n //", "x@" + "9" * 12 + ".0.0"])
def test_a_malformed_entry_is_refused_with_an_example(entry):
    with pytest.raises(tenants.TenantError, match="package@version"):
        tenants.create(CLEAN, extra=[entry])


def test_the_list_is_bounded():
    with pytest.raises(tenants.TenantError, match="at most 10"):
        tenants.create(CLEAN, extra=[f"p{i}@1.0.0" for i in range(11)])


def test_a_refused_list_leaves_no_graph_behind():
    before = len(tenants._tenant_names())
    with pytest.raises(tenants.TenantError):
        tenants.create(CLEAN, extra=["nonsense"])
    assert len(tenants._tenant_names()) == before


def test_the_list_works_over_http_and_is_validated_there_too():
    client = TestClient(create_app(), raise_server_exceptions=False)
    ok = client.post("/api/check", json={"lockfile": GATEWAY.decode(), "extra": ["left-pad@1.3.0"]})
    assert ok.status_code == 200 and len(ok.json()["findings"]) == 7
    assert client.post("/api/check", json={"lockfile": CLEAN.decode(), "extra": ["nonsense"]}).status_code == 422
    assert client.post("/api/check", json={"lockfile": CLEAN.decode(), "extra": ["a@1.0.0"] * 21}).status_code == 422
