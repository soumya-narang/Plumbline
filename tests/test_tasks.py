"""The shared work queue: hand-offs between agents, atomic claiming under contention, and procedural memory."""

import concurrent.futures
import time

import pytest

from plumbline.graph.client import connect, run_named
from plumbline.memory import tasks
from plumbline.memory.replay import seek
from plumbline.timeutil import to_ms

AT = to_ms("2026-08-04T13:00:00Z")
ADVISORY, EXPOSED_ARTIFACT, CLEARED_ARTIFACT = "MAL-2026-11524", "planted/gateway", "planted/orders-api"


@pytest.fixture(autouse=True)
def graph():
    try:
        g = connect()
        n = g.ro_query("MATCH (a:Artifact) RETURN count(a)").result_set[0][0]
    except Exception as exc:
        pytest.skip(f"FalkorDB not available: {exc}")
    if not n:
        pytest.skip("graph is empty")
    wipe(g)
    seek(g, AT, [])  # the recorded incident at 13:00, not whatever an earlier test left behind
    yield g
    wipe(g)
    seek(g, AT, [])


def wipe(g):
    g.query("MATCH (n) WHERE n:Task OR n:Playbook DETACH DELETE n")


def seed(g, n):
    """Many distinct open tasks, written the same way a hand-off writes them."""
    for i in range(n):
        run_named(g, "work/create_task", {"id": f"task:load:{i:03d}", "advisory": ADVISORY, "artifact": EXPOSED_ARTIFACT,
                                          "fix": "bump x", "note": "", "by": "seed", "now_ms": 1_000 + i,}, read_only=False)


def test_an_empty_queue_is_safe_to_read_claim_and_complete(graph):
    assert tasks.list_tasks(graph) == []
    assert tasks.claim(graph, "worker-1") == {"task": None, "message": "no open tasks"}
    with pytest.raises(tasks.WorkError):
        tasks.complete(graph, "task:none", "worker-1", "done")
    assert graph.ro_query("RETURN 1").result_set == [[1]]  # and the database is still answering


def test_handing_off_an_exposed_artifact_carries_the_fix_the_graph_found(graph):
    r = tasks.hand_off(graph, ADVISORY, EXPOSED_ARTIFACT, AT, by="triage-agent", note="  urgent \n now ")
    assert r["created"] and r["status"] == "open" and r["fix"] == "@acme/http-client@1.4.0"
    assert r["path"][-1] == "keyv@6.0.0" and r["recalled"] is None
    (task,) = tasks.list_tasks(graph)
    assert task["created_by"] == "triage-agent" and task["note"] == "urgent now" and task["claimed_by"] is None


def test_handing_off_twice_returns_the_same_task(graph):
    a = tasks.hand_off(graph, ADVISORY, EXPOSED_ARTIFACT, AT, by="triage-agent")
    b = tasks.hand_off(graph, ADVISORY, EXPOSED_ARTIFACT, AT, by="someone-else")
    assert a["task"] == b["task"] and not b["created"] and len(tasks.list_tasks(graph)) == 1


def test_only_an_exposed_artifact_can_be_handed_off(graph):
    with pytest.raises(tasks.WorkError, match="only an EXPOSED artifact"):
        tasks.hand_off(graph, ADVISORY, CLEARED_ARTIFACT, AT, by="triage-agent")
    with pytest.raises(tasks.WorkError, match="no verdict"):
        tasks.hand_off(graph, ADVISORY, "no/such-artifact", AT, by="triage-agent")
    assert tasks.list_tasks(graph) == []


def test_a_hand_off_needs_a_named_agent(graph):
    with pytest.raises(tasks.WorkError, match="agent name"):
        tasks.hand_off(graph, ADVISORY, EXPOSED_ARTIFACT, AT, by="   ")


def test_claiming_takes_the_oldest_open_task_and_marks_it(graph):
    seed(graph, 3)
    first = tasks.claim(graph, "worker-1")["task"]
    assert first["id"] == "task:load:000"
    assert [t["status"] for t in tasks.list_tasks(graph)] == ["claimed", "open", "open"]
    assert tasks.list_tasks(graph, "claimed")[0]["claimed_by"] == "worker-1"


def test_twenty_agents_racing_for_forty_tasks_claim_each_exactly_once(graph):
    seed(graph, 40)
    claimed = []

    def worker(name):
        mine = []
        while (got := tasks.claim(graph, name))["task"]:
            mine.append(got["task"]["id"])
        return mine

    with concurrent.futures.ThreadPoolExecutor(20) as pool:
        for ids in pool.map(worker, [f"w{i}" for i in range(20)]):
            claimed += ids
    assert len(claimed) == 40 and len(set(claimed)) == 40  # nothing twice, nothing missed
    assert all(t["status"] == "claimed" and t["claimed_by"] for t in tasks.list_tasks(graph))


def test_concurrent_handoffs_of_the_same_exposure_make_one_task(graph):
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda i: tasks.hand_off(graph, ADVISORY, EXPOSED_ARTIFACT, AT, by=f"t{i}"), range(8)))
    assert len({r["task"] for r in results}) == 1 and sum(r["created"] for r in results) <= 1
    assert len(tasks.list_tasks(graph)) == 1


def test_only_the_claiming_agent_can_complete_a_task(graph):
    tasks.hand_off(graph, ADVISORY, EXPOSED_ARTIFACT, AT, by="triage-agent")
    tid = tasks.claim(graph, "worker-1")["task"]["id"]
    with pytest.raises(tasks.WorkError, match="not claimed by this agent"):
        tasks.complete(graph, tid, "worker-2", "stole it")
    assert tasks.list_tasks(graph)[0]["status"] == "claimed"
    assert tasks.complete(graph, tid, "worker-1", "bumped to 1.4.1")["status"] == "done"
    with pytest.raises(tasks.WorkError):
        tasks.complete(graph, tid, "worker-1", "again")  # already done


def test_an_open_task_cannot_be_completed_without_claiming_it(graph):
    r = tasks.hand_off(graph, ADVISORY, EXPOSED_ARTIFACT, AT, by="triage-agent")
    with pytest.raises(tasks.WorkError):
        tasks.complete(graph, r["task"], "worker-1", "skipped the claim")


def test_a_resolution_is_required(graph):
    tasks.hand_off(graph, ADVISORY, EXPOSED_ARTIFACT, AT, by="triage-agent")
    tid = tasks.claim(graph, "worker-1")["task"]["id"]
    with pytest.raises(tasks.WorkError, match="resolution"):
        tasks.complete(graph, tid, "worker-1", "  ")


def test_how_a_package_was_fixed_is_recalled_on_the_next_hand_off(graph):
    first = tasks.hand_off(graph, ADVISORY, EXPOSED_ARTIFACT, AT, by="triage-agent")
    tid = tasks.claim(graph, "worker-1")["task"]["id"]
    done = tasks.complete(graph, tid, "worker-1", "bumped @acme/http-client to 1.4.1")
    assert done["playbook"] == "bump:keyv" and done["times_used"] == 1
    second = tasks.hand_off(graph, ADVISORY, "planted/storefront", AT, by="triage-agent")
    assert first["recalled"] is None
    assert second["recalled"] == {"resolution": "bumped @acme/http-client to 1.4.1", "times_used": 1}


def test_the_playbook_counts_every_use_and_keeps_the_latest_resolution(graph):
    for artifact, how in ((EXPOSED_ARTIFACT, "pinned keyv 5"), ("planted/storefront", "upgraded payments-sdk")):
        tasks.hand_off(graph, ADVISORY, artifact, AT, by="triage-agent")
        tid = tasks.claim(graph, "worker-1")["task"]["id"]
        done = tasks.complete(graph, tid, "worker-1", how)
    assert done["times_used"] == 2
    assert graph.ro_query("MATCH (p:Playbook) RETURN p.last_resolution, p.uses").result_set == [["upgraded payments-sdk", 2]]


def test_the_queue_is_bounded(graph, monkeypatch):
    monkeypatch.setattr(tasks, "MAX_OPEN", 1)
    tasks.hand_off(graph, ADVISORY, EXPOSED_ARTIFACT, AT, by="triage-agent")
    with pytest.raises(tasks.WorkError, match="already holds 1 unfinished"):
        tasks.hand_off(graph, ADVISORY, "planted/storefront", AT, by="triage-agent")


def test_listing_filters_by_status_and_rejects_nonsense(graph):
    seed(graph, 2)
    tasks.claim(graph, "w")
    assert [t["status"] for t in tasks.list_tasks(graph, "open")] == ["open"]
    assert len(tasks.list_tasks(graph, "done")) == 0
    with pytest.raises(tasks.WorkError):
        tasks.list_tasks(graph, "x' MATCH (n) DETACH DELETE n //")


def test_replaying_the_incident_never_touches_the_work_queue(graph):
    tasks.hand_off(graph, ADVISORY, EXPOSED_ARTIFACT, AT, by="triage-agent")
    for hour in ("08", "13", "09"):
        seek(graph, to_ms(f"2026-08-04T{hour}:00:00Z"), [])
    assert len(tasks.list_tasks(graph)) == 1


def test_a_claim_is_fast_even_with_a_full_queue(graph):
    seed(graph, tasks.MAX_OPEN)
    started = time.time()
    tasks.claim(graph, "w")
    assert time.time() - started < 1.0


def test_an_exposure_that_rests_on_a_hypothetical_revision_never_enters_the_shared_queue(graph):
    seek(graph, to_ms("2026-08-04T13:00:00Z"), [])  # the graph now carries the scripted 12:45 revision
    # billing-worker locks keyv@6.0.1, which only that revision adds to the advisory
    with pytest.raises(tasks.WorkError, match="hypothetical advisory revision"):
        tasks.hand_off(graph, ADVISORY, "planted/billing-worker", to_ms("2026-08-04T13:00:00Z"), by="triage-agent")
    assert tasks.list_tasks(graph) == []
    # gateway locks keyv@6.0.0, which the advisory names as published, so it is real work
    assert tasks.hand_off(graph, ADVISORY, EXPOSED_ARTIFACT, AT, by="triage-agent")["created"]
    assert [t["artifact"] for t in tasks.list_tasks(graph)] == [EXPOSED_ARTIFACT]


def test_a_visitors_what_if_cannot_put_work_in_the_shared_queue(graph):
    # mocha locks keyv@4.5.4; a what-if that names it makes mocha look exposed, but only for the person who asked
    events = [{"at": "2026-08-04T12:30:00Z", "type": "advisory_revised", "scripted": True, "visitor": True,
               "advisory": ADVISORY, "add_purls": ["pkg:npm/keyv@4.5.4"]}]
    seek(graph, to_ms("2026-08-04T12:31:00Z"), events)
    with pytest.raises(tasks.WorkError, match="hypothetical"):
        tasks.hand_off(graph, ADVISORY, "mochajs/mocha", to_ms("2026-08-04T12:31:00Z"), by="triage-agent")
    assert tasks.list_tasks(graph) == []


def test_a_real_exposure_keeps_a_real_path_and_fix_even_when_a_what_if_adds_a_second_route(graph):
    # storefront locks keyv@6.0.0 (named by the advisory) and keyv@4.5.4 (named only by this what-if, through eslint)
    what_if = [{"at": "2026-08-04T12:30:00Z", "type": "advisory_revised", "scripted": True, "visitor": True,
                "advisory": ADVISORY, "add_purls": ["pkg:npm/keyv@4.5.4"]}]
    seek(graph, to_ms("2026-08-04T12:31:00Z"), what_if)
    r = tasks.hand_off(graph, ADVISORY, "planted/storefront", to_ms("2026-08-04T12:31:00Z"), by="triage-agent")
    assert r["created"] and r["path"][-1] == "keyv@6.0.0"
    assert r["fix"] == "@acme/payments-sdk@2.1.0"  # not eslint, which only the hypothetical route goes through
