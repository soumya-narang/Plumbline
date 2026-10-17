"""The multi-agent demonstration and the queue's HTTP surface."""

import pytest
from fastapi.testclient import TestClient

from plumbline.api.app import create_app
from plumbline.graph.client import connect
from plumbline.memory.handoff_demo import run_demo
from plumbline.memory.replay import seek
from plumbline.timeutil import to_ms

AT = to_ms("2026-08-04T13:00:00Z")


@pytest.fixture(autouse=True)
def graph():
    try:
        g = connect()
        n = g.ro_query("MATCH (a:Artifact) RETURN count(a)").result_set[0][0]
    except Exception as exc:
        pytest.skip(f"FalkorDB not available: {exc}")
    if not n:
        pytest.skip("graph is empty")
    g.query("MATCH (n) WHERE n:Task OR n:Playbook DETACH DELETE n")
    seek(g, AT, [])
    yield g
    g.query("MATCH (n) WHERE n:Task OR n:Playbook DETACH DELETE n")


@pytest.mark.parametrize("workers", [1, 4, 16])
def test_every_exposure_is_worked_exactly_once_whatever_the_number_of_agents(graph, workers):
    out = run_demo(graph, AT, workers)
    assert out["handed_off"] >= 3 and out["newly_queued"] == out["handed_off"]
    assert out["claimed"] == out["newly_queued"] and out["claimed_twice"] == 0 and out["exactly_once"]
    assert sum(out["per_worker"].values()) == out["claimed"]
    assert graph.ro_query("MATCH (t:Task) WHERE t.status <> 'done' RETURN count(t)").result_set == [[0]]


def test_a_second_run_finds_nothing_new_and_does_not_redo_finished_work(graph):
    run_demo(graph, AT, 4)
    again = run_demo(graph, AT, 4)
    assert again["newly_queued"] == 0 and again["claimed"] == 0 and again["exactly_once"]


def test_what_one_run_learned_is_offered_in_the_next(graph):
    run_demo(graph, AT, 2, round_name="first")
    graph.query("MATCH (t:Task) DETACH DELETE t")  # a new incident for the same package: fresh tasks, same playbook memory
    again = run_demo(graph, AT, 2, round_name="second")
    assert again["recalled_playbooks"] and all("first round" in r for r in again["recalled_playbooks"])


def test_the_queue_is_readable_over_http_and_validates_its_filter(graph):
    client = TestClient(create_app(), raise_server_exceptions=False)
    assert client.get("/api/tasks").json() == {"tasks": []}
    run_demo(graph, AT, 2)
    done = client.get("/api/tasks", params={"status": "done"}).json()["tasks"]
    assert len(done) >= 3 and all(t["claimed_by"].startswith("remediation-") and t["resolution"] for t in done)
    assert client.get("/api/tasks", params={"status": "bogus"}).status_code == 422
    assert client.post("/api/tasks").status_code in (404, 405)  # nobody writes the queue over HTTP; agents do, over MCP
