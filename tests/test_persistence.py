"""Approvals are decisions, so they survive a restart; what-ifs are hypothetical, so they do not."""

import json

import pytest
from fastapi.testclient import TestClient

from plumbline.api import app as app_module
from plumbline.api.sessions import Approvals, state_file
from plumbline.graph.client import connect

SESSION = "a" * 32
OTHER = "b" * 32
AT = "2026-08-04T12:30:00Z"


def approval(name="Ada", artifact="planted/gateway"):
    return {"at": AT, "type": "approve", "advisory": "MAL-2026-11524", "artifact": artifact, "approver": name, "manual": True}


def what_if():
    return {"at": AT, "type": "advisory_revised", "scripted": True, "visitor": True, "advisory": "MAL-2026-11524",
            "add_purls": ["pkg:npm/keyv@4.5.4"]}


@pytest.fixture()
def path(tmp_path):
    return tmp_path / "state" / "approvals.jsonl"


def test_an_approval_survives_a_restart(path):
    Approvals(path=path).add(SESSION, "client", approval("Ada"))
    assert Approvals(path=path).history(SESSION) == [approval("Ada")]


def test_a_what_if_does_not_survive_a_restart(path):
    first = Approvals(path=path)
    first.add(SESSION, "client", what_if())
    first.add(SESSION, "client", approval("Ada"))
    assert Approvals(path=path).history(SESSION) == [approval("Ada")]


def test_visitors_get_back_only_their_own_approvals(path):
    first = Approvals(path=path)
    first.add(SESSION, "c1", approval("Ada"))
    first.add(OTHER, "c2", approval("Bo"))
    second = Approvals(path=path)
    assert [e["approver"] for e in second.history(SESSION)] == ["Ada"]
    assert [e["approver"] for e in second.history(OTHER)] == ["Bo"]


def test_removing_what_ifs_keeps_the_approvals():
    store = Approvals()
    store.add(SESSION, "c", approval("Ada"))
    store.add(SESSION, "c", what_if())
    store.clear_what_ifs(SESSION)
    assert store.history(SESSION) == [approval("Ada")]


def test_removing_what_ifs_leaves_nothing_behind_when_there_were_no_approvals():
    store = Approvals()
    store.add(SESSION, "c", what_if())
    store.clear_what_ifs(SESSION)
    assert store.history(SESSION) == [] and store.digest(SESSION) == ""


def test_the_approvals_kept_after_removing_what_ifs_are_still_on_disk_after_a_restart(path):
    store = Approvals(path=path)
    store.add(SESSION, "c", approval("Ada"))
    store.add(SESSION, "c", what_if())
    store.clear_what_ifs(SESSION)
    assert Approvals(path=path).history(SESSION) == [approval("Ada")]


def test_a_damaged_file_is_survived_line_by_line(path):
    path.parent.mkdir(parents=True)
    good = json.dumps({"session": SESSION, "event": approval("Ada")})
    path.write_text("\n".join([
        "not json at all",
        good,
        json.dumps({"session": "../../etc/passwd", "event": approval("Mallory")}),   # not a session id
        json.dumps({"session": SESSION, "event": {**approval("X"), "type": "advisory_revised"}}),  # not an approval
        json.dumps({"session": SESSION, "event": {**approval("Y"), "approver": 7}}),  # wrong type
        json.dumps({"session": SESSION}),
        json.dumps(["list"]),
        '{"session": "' + SESSION + '", "event": ',  # cut off mid-write
        "",
    ]), encoding="utf-8")
    assert Approvals(path=path).history(SESSION) == [approval("Ada")]


def test_unknown_fields_in_a_stored_event_are_not_carried_into_the_replay(path):
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"session": SESSION, "event": {**approval("Ada"), "scripted": True, "add_purls": ["x"]}}) + "\n", encoding="utf-8")
    (event,) = Approvals(path=path).history(SESSION)
    assert "scripted" not in event and "add_purls" not in event


def test_loading_rewrites_the_file_compactly(path):
    store = Approvals(path=path, max_per_session=2)
    for name in ("A", "B", "C", "D"):
        store.add(SESSION, "c", approval(name)) if len(store.history(SESSION)) < 2 else None
    path.write_text(path.read_text(encoding="utf-8") * 3, encoding="utf-8")  # a bloated file
    reloaded = Approvals(path=path, max_per_session=2)
    assert len(reloaded.history(SESSION)) == 2
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_old_sessions_drop_out_of_the_file_too(path):
    store = Approvals(path=path, max_sessions=2)
    for i in range(4):
        store.add(f"{i:032x}", "c", approval(f"p{i}"))
    kept = {json.loads(line)["session"] for line in path.read_text(encoding="utf-8").splitlines()}
    assert kept == {f"{2:032x}", f"{3:032x}"}
    assert {s for s in kept if Approvals(path=path, max_sessions=2).history(s)} == kept


def test_no_temporary_file_is_left_behind(path):
    Approvals(path=path).add(SESSION, "c", approval("Ada"))
    Approvals(path=path)
    assert [p.name for p in path.parent.iterdir()] == ["approvals.jsonl"]


def test_state_is_kept_under_the_chosen_directory_or_switched_off(monkeypatch, tmp_path):
    monkeypatch.setenv("PLUMBLINE_STATE_DIR", str(tmp_path / "elsewhere"))
    assert state_file() == tmp_path / "elsewhere" / "approvals.jsonl"
    monkeypatch.setenv("PLUMBLINE_STATE_DIR", "off")
    assert state_file() is None
    monkeypatch.delenv("PLUMBLINE_STATE_DIR")
    assert state_file().parts[-2:] == ("state", "approvals.jsonl")


def test_without_a_file_nothing_is_written_anywhere(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Approvals().add(SESSION, "c", approval("Ada"))
    assert list(tmp_path.iterdir()) == []


# ---- through the HTTP layer, the way a visitor meets it

@pytest.fixture()
def live(path, monkeypatch):
    try:
        n = connect().ro_query("MATCH (a:Artifact) RETURN count(a)").result_set[0][0]
    except Exception as exc:
        pytest.skip(f"FalkorDB not available: {exc}")
    if not n:
        pytest.skip("graph is empty")
    monkeypatch.setattr(app_module, "approvals", Approvals(path=path))
    app_module._cache.clear()
    return path


def approvers(client, at=AT):
    return {d["approver"] for d in client.get("/api/snapshot", params={"at": at}).json()["decisions"]}


def test_a_visitors_approval_is_still_theirs_after_the_server_restarts(live, monkeypatch):
    client = TestClient(app_module.create_app())
    body = {"advisory": "MAL-2026-11524", "artifact": "planted/gateway", "at": AT, "approver": "Ada"}
    assert client.post("/api/approve", json=body).status_code == 200
    assert "Ada" in approvers(client)

    monkeypatch.setattr(app_module, "approvals", Approvals(path=live))  # a restart: new process, same file
    app_module._cache.clear()
    assert "Ada" in approvers(client)  # same cookie, so the same visitor
    assert "Ada" not in approvers(TestClient(app_module.create_app()))  # a different visitor still does not see it


def test_the_remove_what_ifs_button_keeps_the_approvals(live):
    client = TestClient(app_module.create_app())
    client.post("/api/approve", json={"advisory": "MAL-2026-11524", "artifact": "planted/gateway", "at": AT, "approver": "Ada"})
    assert client.post("/api/revise", json={"advisory": "MAL-2026-11524", "version": "4.5.4", "at": AT}).status_code == 200
    events = client.get("/api/snapshot", params={"at": AT}).json()["events"]
    assert any(e["visitor"] for e in events)

    assert client.delete("/api/revise").json() == {"cleared": True}
    snap = client.get("/api/snapshot", params={"at": AT}).json()
    assert not any(e["visitor"] for e in snap["events"])
    assert "Ada" in {d["approver"] for d in snap["decisions"]}
