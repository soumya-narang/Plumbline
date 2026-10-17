"""Tests for the MCP server, the built-in planner and the model backend (mocked; no key is needed)."""

import asyncio
import json
from dataclasses import replace

import httpx
import pytest
from mcp.client import Client

from plumbline import config
from plumbline.agent.mcp_server import build_server
from plumbline.agent.runner import ask
from plumbline.agent.tools import READ_TOOLS, TOOLS, WORK_TOOLS
from plumbline.graph.client import connect
from plumbline.memory.replay import reset, seek
from plumbline.timeutil import to_ms

AFTER = "2026-08-04T13:00:00Z"
BEFORE = "2026-08-04T12:00:00Z"


@pytest.fixture(autouse=True)
def graph_state():
    try:
        g = connect()
        n = g.ro_query("MATCH (a:Artifact) RETURN count(a)").result_set[0][0]
    except Exception as exc:
        pytest.skip(f"FalkorDB not available: {exc}")
    if not n:
        pytest.skip("graph is empty; run `python -m plumbline load`")
    yield g
    reset(g)


def run(coro):
    return asyncio.run(coro)


def test_server_exposes_the_read_tools_and_a_work_queue_and_nothing_else():
    async def go():
        async with Client(build_server()) as c:
            tools = (await c.list_tools()).tools
            return {t.name: t.annotations for t in tools}

    exposed = run(go())
    assert set(exposed) == set(TOOLS) == set(READ_TOOLS) | set(WORK_TOOLS)
    assert all(exposed[n].read_only_hint for n in READ_TOOLS)
    assert exposed["list_tasks"].read_only_hint
    assert not exposed["claim_task"].read_only_hint and not any(a.destructive_hint for a in exposed.values())
    assert "commit_decision" not in exposed  # approval is a human action, never a tool


def test_tool_call_over_mcp_returns_the_policy_verdict():
    async def go():
        async with Client(build_server()) as c:
            res = await c.call_tool("triage_advisory", {"advisory": "MAL-2026-11524", "at": "2026-08-04T11:40:00Z"})
            return json.loads("".join(x.text for x in res.content))

    data = run(go())
    assert data["counts"] == {"EXPOSED": 2, "CLEARED": 13, "UNKNOWN": 3}
    assert data["rows"][0]["artifact"] == "planted/gateway" and data["rows"][0]["receipt"]


def test_propose_decision_writes_nothing(graph_state):
    from plumbline.agent.tools import propose_decision

    out = propose_decision("MAL-2026-11524", "planted/gateway", BEFORE)
    assert out["written"] is False and out["requires_human_approval"] is True
    assert graph_state.ro_query("MATCH (d:Decision) RETURN count(d)").result_set[0][0] == 0


def test_planner_answers_with_a_path_and_names_its_tools():
    r = run(ask("Why is the edge gateway exposed?", BEFORE))
    assert r.backend == "planner" and r.model is None
    assert [c.name for c in r.calls] == ["list_advisories", "triage_advisory", "explain_path"]
    assert "@acme/http-client@1.4.0" in r.answer and "keyv@6.0.0" in r.answer


def test_planner_refuses_to_guess_when_evidence_is_missing():
    r = run(ask("Is eslint affected by the keyv compromise?", BEFORE))
    assert "UNKNOWN" in r.answer and "no lockfile" in r.answer and "CLEARED" not in r.answer.split("eslint")[-1]


def test_planner_notices_the_reopened_decision(graph_state):
    seek(graph_state, to_ms(AFTER))
    r = run(ask("Is anything we already decided no longer valid?", AFTER))
    assert "planted/billing-worker" in r.answer and "keyv@6.0.1" in r.answer and "EXPOSED" in r.answer


def test_nothing_published_yet_is_reported_honestly():
    r = run(ask("What is exposed?", "2026-08-04T11:00:00Z"))
    assert "nothing to assess" in r.answer


def _fake_model():
    """A stand-in chat-completions server: first asks for a tool, then answers using the tool result."""
    seen = {"requests": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["requests"] += 1
        body = json.loads(request.content)
        if seen["requests"] == 1:
            assert body["tools"] and {t["function"]["name"] for t in body["tools"]} == set(TOOLS)
            msg = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": "triage_advisory",
                             "arguments": json.dumps({"advisory": "MAL-2026-11524", "at": BEFORE})}}]}
        else:
            tool_msg = next(m for m in body["messages"] if m["role"] == "tool")
            counts = json.loads(tool_msg["content"])["counts"]
            msg = {"role": "assistant", "content": f"{counts['EXPOSED']} service(s) exposed."}
        return httpx.Response(200, json={"choices": [{"message": msg}]})

    return httpx.MockTransport(handler), seen


def test_model_backend_selects_tools_over_mcp_and_answers():
    settings = replace(config.load_settings(), llm_base_url="http://model.test/v1", llm_api_key="k", llm_model="m")
    transport, seen = _fake_model()
    r = run(ask("What is exposed?", BEFORE, settings=settings, backend="llm", transport=transport))
    assert r.backend == "llm" and r.model == "m"
    assert [c.name for c in r.calls] == ["triage_advisory"] and r.calls[0].error is None
    assert r.answer == "2 service(s) exposed." and seen["requests"] == 2


def test_model_backend_requires_configuration():
    settings = replace(config.load_settings(), llm_base_url=None, llm_model=None)
    with pytest.raises(RuntimeError):
        run(ask("hi", BEFORE, settings=settings, backend="llm"))


def _model_settings():
    return replace(config.load_settings(), llm_base_url="http://model.test/v1", llm_api_key="k", llm_model="m")


def _answer_with(handler):
    return run(ask("What is exposed?", BEFORE, settings=_model_settings(), backend="llm", transport=httpx.MockTransport(handler)))


def test_a_model_that_is_down_falls_back_to_the_planner_and_says_so():
    def handler(request):
        raise httpx.ConnectError("connection refused")

    r = _answer_with(handler)
    assert r.backend == "planner" and r.model is None and r.calls
    assert "could not be used" in r.note and "connection refused" in r.note


def test_a_model_that_times_out_falls_back():
    def handler(request):
        raise httpx.ReadTimeout("slow")

    assert _answer_with(handler).backend == "planner"


def test_a_server_error_from_the_model_falls_back():
    r = _answer_with(lambda request: httpx.Response(500, json={"error": "overloaded"}))
    assert r.backend == "planner" and "500" in r.note


def test_a_model_that_answers_without_using_a_tool_is_not_believed():
    msg = {"role": "assistant", "content": "Everything is fine, trust me."}
    r = _answer_with(lambda request: httpx.Response(200, json={"choices": [{"message": msg}]}))
    assert r.backend == "planner" and "not grounded" in r.note and "Everything is fine" not in r.answer


def test_tool_arguments_that_are_not_json_fall_back():
    msg = {"role": "assistant", "content": None, "tool_calls": [{
        "id": "c", "type": "function", "function": {"name": "triage_advisory", "arguments": "{not json"}}]}
    r = _answer_with(lambda request: httpx.Response(200, json={"choices": [{"message": msg}]}))
    assert r.backend == "planner" and "not valid JSON" in r.note


def test_a_reply_with_no_choices_falls_back():
    assert _answer_with(lambda request: httpx.Response(200, json={"choices": []})).backend == "planner"


def test_the_model_timeout_comes_from_settings(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT", "450")
    assert config.load_settings().llm_timeout == 450.0
    monkeypatch.delenv("LLM_TIMEOUT")
    assert config.load_settings().llm_timeout == 120.0


def _data(result):
    """A tool result as the runner reads it: structured content when present, otherwise the JSON text."""
    return result.structured_content or json.loads("".join(c.text for c in result.content))


def test_the_planner_hands_every_exposed_artifact_to_the_queue_and_lists_it():
    from plumbline.graph.client import connect
    from plumbline.memory.replay import seek
    from plumbline.timeutil import to_ms

    g = connect()
    g.query("MATCH (n) WHERE n:Task OR n:Playbook DETACH DELETE n")
    seek(g, to_ms(AFTER), [])  # the graph now carries the scripted 12:45 revision
    try:
        r = run(ask("Hand off the fixes for keyv", AFTER))
        assert "hand_off_fix" in [c.name for c in r.calls]
        assert "planted/gateway: fix queued, bump @acme/http-client@1.4.0" in r.answer
        assert "1 exposure would exist only if a hypothetical advisory revision were real" in r.answer
        assert "billing-worker" not in r.answer.split("hypothetical")[0]
        again = run(ask("Hand off the fixes for keyv", AFTER))
        assert "already in the queue (open)" in again.answer
        q = run(ask("What is in the work queue?", AFTER))
        assert [c.name for c in q.calls][-1] == "list_tasks" and "planted/gateway open" in q.answer
    finally:
        g.query("MATCH (n) WHERE n:Task OR n:Playbook DETACH DELETE n")


def test_two_agents_over_mcp_pass_a_fix_without_sharing_anything_but_the_graph():
    from plumbline.graph.client import connect

    g = connect()
    g.query("MATCH (n) WHERE n:Task OR n:Playbook DETACH DELETE n")

    async def triage_then_remediate():
        async with Client(build_server()) as triage, Client(build_server()) as remediation:
            handed = _data(await triage.call_tool("hand_off_fix", {
                "advisory": "MAL-2026-11524", "artifact": "planted/gateway", "at": AFTER, "agent": "triage"}))
            got = _data(await remediation.call_tool("claim_task", {"agent": "remediation"}))
            nothing_left = _data(await triage.call_tool("claim_task", {"agent": "triage"}))
            done = _data(await remediation.call_tool("complete_task", {
                "task_id": got["task"]["id"], "agent": "remediation", "resolution": "bumped @acme/http-client"}))
            refused = _data(await triage.call_tool("complete_task", {
                "task_id": got["task"]["id"], "agent": "triage", "resolution": "not mine"}))
            return handed, got, nothing_left, done, refused

    try:
        handed, got, nothing_left, done, refused = run(triage_then_remediate())
        assert handed["created"] and got["task"]["id"] == handed["task"] and got["task"]["fix"] == "@acme/http-client@1.4.0"
        assert nothing_left["task"] is None and done["status"] == "done" and "error" in refused
    finally:
        g.query("MATCH (n) WHERE n:Task OR n:Playbook DETACH DELETE n")


def test_a_work_tool_refuses_an_artifact_that_is_not_exposed_as_data_not_a_crash():
    async def go():
        async with Client(build_server()) as c:
            return _data(await c.call_tool("hand_off_fix", {
                "advisory": "MAL-2026-11524", "artifact": "planted/orders-api", "at": AFTER}))

    assert "only an EXPOSED artifact" in run(go())["error"]


def test_a_what_if_cannot_make_the_planner_flood_the_queue():
    from plumbline.graph.client import connect
    from plumbline.memory.replay import seek
    from plumbline.timeutil import to_ms

    g = connect()
    g.query("MATCH (n) WHERE n:Task OR n:Playbook DETACH DELETE n")
    try:
        what_if = [{"at": "2026-08-04T12:30:00Z", "type": "advisory_revised", "scripted": True, "visitor": True,
                    "advisory": "MAL-2026-11524", "add_purls": ["pkg:npm/keyv@4.5.4"]}]
        seek(g, to_ms(AFTER), what_if)  # twelve more repositories now look exposed, for this visitor only
        r = run(ask("Hand off the fixes for keyv", AFTER))
        assert "exposures would exist only if a hypothetical advisory revision were real" in r.answer
        queued = g.ro_query("MATCH (t:Task) RETURN t.artifact ORDER BY t.artifact").result_set
        assert [row[0] for row in queued] == ["planted/gateway", "planted/storefront"]  # only the real ones
    finally:
        g.query("MATCH (n) WHERE n:Task OR n:Playbook DETACH DELETE n")
