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
from plumbline.agent.tools import TOOLS
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


def test_server_exposes_exactly_the_read_only_tools():
    async def go():
        async with Client(build_server()) as c:
            tools = (await c.list_tools()).tools
            return {t.name: t.annotations for t in tools}

    exposed = run(go())
    assert set(exposed) == set(TOOLS)
    assert all(a is not None and a.read_only_hint for a in exposed.values())
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
