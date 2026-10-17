"""Run the agent: choose tools over MCP, record every call, and compose an answer.

Two interchangeable backends share one trace format:

* ``planner``  a built-in rule-based planner. No model, no key, deterministic. Always available.
* ``llm``      any server speaking the common chat-completions tool-calling protocol (set LLM_BASE_URL,
               LLM_API_KEY, LLM_MODEL). The model selects tools and phrases the answer.

Either way the agent reaches the graph only through the MCP server, and the UI draws verdicts from tool results
rather than from the answer's prose.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field

import httpx
from mcp.client import Client

from plumbline import config
from plumbline.agent.mcp_server import build_server
from plumbline.triage.serialize import fact_label

MAX_STEPS = 6


@dataclass
class ToolCall:
    name: str
    args: dict
    result: dict
    ms: int
    error: str | None = None


@dataclass
class AgentRun:
    question: str
    at: str
    backend: str  # "planner" or "llm"
    model: str | None
    calls: list[ToolCall] = field(default_factory=list)
    answer: str = ""
    note: str | None = None  # set when the model could not be used and the planner answered instead

    def to_dict(self) -> dict:
        return asdict(self)


async def call_tool(client: Client, run: AgentRun, name: str, args: dict) -> dict:
    started = time.perf_counter()
    error = None
    try:
        res = await client.call_tool(name, args)
        text = "".join(getattr(c, "text", "") for c in res.content)
        data = res.structured_content if getattr(res, "structured_content", None) else (json.loads(text) if text else {})
        if res.is_error:
            error, data = text or "tool error", {"error": text}
    except Exception as exc:  # noqa: BLE001  a tool failure must be reported in the trace, not crash the run
        error, data = str(exc), {"error": str(exc)}
    run.calls.append(ToolCall(name, args, data, int((time.perf_counter() - started) * 1000), error))
    return data


# ---------------------------------------------------------------- built-in planner

_ADVISORY_ID = re.compile(r"MAL-\d{4}-\d+", re.IGNORECASE)
_REOPEN = re.compile(r"reopen|stale|invalidat|changed|no longer|reconsider|still valid", re.IGNORECASE)
_DECISIONS = re.compile(r"\bdecision|decided|approved|accepted risk", re.IGNORECASE)
_PROPOSE = re.compile(r"propose|should we approve|approve|sign off|what would you decide", re.IGNORECASE)
_EXPLAIN = re.compile(r"why|path|how|explain|chain|evidence|prove", re.IGNORECASE)
_FIX = re.compile(r"upgrade|bump|fix first|fix-first|patch first|remediat|update first|what should we (fix|do)", re.IGNORECASE)
_CRITICAL = re.compile(r"critical|central|lean on|depends? on most|most important|pagerank|hub|concentrat|riskiest", re.IGNORECASE)


def _pick_advisory(question: str, advisories: list[dict]) -> str | None:
    if not advisories:
        return None
    m = _ADVISORY_ID.search(question)
    if m and any(a["id"].lower() == m.group(0).lower() for a in advisories):
        return next(a["id"] for a in advisories if a["id"].lower() == m.group(0).lower())
    q = question.lower()
    # longest package name first so "@cacheable/net" beats "cacheable"
    for a in sorted(advisories, key=lambda a: -len(a["package"])):
        if a["package"].lower() in q:
            return a["id"]
    exposed_first = [a for a in advisories if a["package"] == "keyv"]
    return (exposed_first or advisories)[0]["id"]


def _pick_artifact(question: str, rows: list[dict]) -> str | None:
    q = question.lower()
    best = None
    for r in rows:
        tokens = {r["artifact"].lower(), r["artifact"].split("/")[-1].lower(), (r.get("service") or "").lower()}
        if any(t and t in q for t in tokens):
            best = r["artifact"]
            if r["artifact"].lower() in q:
                break
    return best


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _fmt_path(path: list[str] | None) -> str:
    return " -> ".join(path) if path else ""


async def run_planner(client: Client, run: AgentRun) -> None:
    q = run.question
    listing = await call_tool(client, run, "list_advisories", {"at": run.at})
    advisories = listing.get("advisories", [])
    lines: list[str] = []

    if _REOPEN.search(q) and not _ADVISORY_ID.search(q):
        res = await call_tool(client, run, "reopen_check", {"at": run.at})
        reopened = res.get("decisions", [])
        if not reopened:
            lines.append(f"No decision has a contradicted assumption as of {run.at}.")
        for d in reopened:
            ex = await call_tool(client, run, "explain_path",
                                 {"advisory": d["advisory"], "artifact": d["artifact"], "at": run.at})
            lines.append(f"{d['artifact']} was decided {d['decided_verdict']} for {d['advisory']}, but it assumed "
                         f"that {'; '.join(fact_label(a) for a in d['broken_assumptions'])}, which stopped being true at {d['broken_at']}. "
                         f"It is now {ex.get('verdict', '?')}"
                         + (f" via {_fmt_path(ex.get('path'))}." if ex.get("path")
                            else f" ({ex.get('evidence') and ', '.join(e['purl'] for e in ex['evidence'])})."))
    elif _FIX.search(q):
        advisory = _pick_advisory(q, advisories)
        if advisory is None:
            run.answer = f"No advisory has been published as of {run.at}, so there is nothing to fix yet."
            return
        res = await call_tool(client, run, "fix_first", {"advisory": advisory, "at": run.at})
        bump = res.get("bump", [])
        if not bump:
            lines.append(f"No artifact is exposed to {advisory} as of {run.at}, so nothing needs upgrading.")
        else:
            top = bump[0]
            lines.append(f"Upgrade {top['package']} first: it pulls the affected versions into {_plural(top['artifacts'], 'artifact')} "
                         f"({', '.join(top['in_artifacts'])}).")
            for other in bump[1:]:
                lines.append(f"Then {other['package']} ({', '.join(other['in_artifacts'])}).")
    elif _CRITICAL.search(q):
        advisory = _pick_advisory(q, advisories)
        tri = await call_tool(client, run, "triage_advisory", {"advisory": advisory, "at": run.at, "include_cleared": True}) if advisory else {}
        target = _pick_artifact(q, tri.get("rows", [])) or "planted/storefront"
        res = await call_tool(client, run, "critical_dependencies", {"artifact": target, "limit": 5})
        pk = res.get("packages", [])
        lines.append(
            f"{target} leans most on {', '.join(p['package'] for p in pk)} (PageRank over its dependency graph). "
            "A compromise of any of these reaches the largest part of its tree."
            if pk else f"No dependency graph is available for {target}.")
    elif _DECISIONS.search(q) and not _PROPOSE.search(q):
        res = await call_tool(client, run, "list_decisions", {})
        ds = res.get("decisions", [])
        lines.append(f"{len(ds)} decisions recorded: " + "; ".join(
            f"{d['artifact']} {d['verdict']} ({d['status']})" for d in ds) + "." if ds else "No decisions recorded yet.")
    else:
        advisory = _pick_advisory(q, advisories)
        if advisory is None:
            run.answer = f"No advisory has been published as of {run.at}, so there is nothing to assess yet."
            return
        tri = await call_tool(client, run, "triage_advisory", {"advisory": advisory, "at": run.at, "include_cleared": True})
        rows = tri.get("rows", [])
        target = _pick_artifact(q, rows)
        if _PROPOSE.search(q) and target:
            p = await call_tool(client, run, "propose_decision", {"advisory": advisory, "artifact": target, "at": run.at})
            lines.append(f"Proposed for {target}: {p.get('verdict')} -> {p.get('proposed_action')}; it would assume "
                         f"{_plural(len(p.get('would_assume', [])), 'fact')}. Nothing was written; a person must approve it.")
        elif target or _EXPLAIN.search(q):
            subject = target or next((r["artifact"] for r in rows if r["verdict"] == "EXPOSED"), None)
            if subject:
                ex = await call_tool(client, run, "explain_path", {"advisory": advisory, "artifact": subject, "at": run.at})
                lines.append(_explain_line(ex))
            else:
                lines.append(f"No artifact is exposed to {advisory} as of {run.at}.")
        else:
            c = tri.get("counts", {})
            lines.append(f"{advisory} ({tri.get('package')}) as of {run.at}: {c.get('EXPOSED', 0)} exposed, "
                         f"{c.get('UNKNOWN', 0)} unknown, {c.get('CLEARED', 0)} cleared.")
            for r in rows:
                if r["verdict"] == "EXPOSED":
                    lines.append(f"EXPOSED {r['artifact']}: {_fmt_path(r['path'])} (receipt {r['receipt'][:12]}).")
            for r in rows:
                if r["verdict"] == "UNKNOWN":
                    lines.append(f"UNKNOWN {r['artifact']}: {r['reason'].replace('_', ' ')}; refusing to guess.")
    run.answer = " ".join(lines)


def _explain_line(ex: dict) -> str:
    if "error" in ex:
        return ex["error"]
    v, art = ex["verdict"], ex["artifact"]
    if v == "EXPOSED":
        return (f"{art} is EXPOSED to {ex['advisory']}: it locks {', '.join(e['purl'] for e in ex['evidence'])}, "
                f"reached via {_fmt_path(ex['path'])}. Receipt {ex['receipt'][:12]}.")
    if v == "CLEARED":
        locked = ", ".join(e["version"] for e in ex["evidence"]) or "none"
        return (f"{art} is CLEARED for {ex['advisory']}: it locks versions [{locked}] of the package, none named by the "
                f"advisory. That holds only while {_plural(len(ex['assumptions']), 'assumption')} stay true.")
    return f"{art} is UNKNOWN for {ex['advisory']}: {ex['reason'].replace('_', ' ')}. The agent refuses to guess."


# ---------------------------------------------------------------- model backend

SYSTEM_PROMPT = (
    "You are Plumbline, a supply-chain exposure analyst. Use the tools to answer; never guess. Verdicts "
    "(EXPOSED, CLEARED, UNKNOWN) are produced by the tools' deterministic policy: quote them exactly and never "
    "upgrade UNKNOWN to CLEARED. For EXPOSED results cite the dependency path and receipt hash; for UNKNOWN say "
    "what evidence is missing. Answer in a few plain sentences. Current time: {at}. Pass it as the 'at' argument."
)


def _chat_tools(tool_list) -> list[dict]:
    return [{"type": "function", "function": {
        "name": t.name, "description": t.description or "", "parameters": t.input_schema}} for t in tool_list]


class ModelUnusable(Exception):
    """The model backend failed or produced something the agent will not present; the message says why."""


def _parse_args(raw: str | None) -> dict:
    try:
        args = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ModelUnusable("the model sent tool arguments that are not valid JSON") from exc
    if not isinstance(args, dict):
        raise ModelUnusable("the model sent tool arguments that are not an object")
    return args


async def run_llm(client: Client, run: AgentRun, settings: config.Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
    tools = _chat_tools((await client.list_tools()).tools)
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(at=run.at)}, {"role": "user", "content": run.question}]
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"} if settings.llm_api_key else {}
    async with httpx.AsyncClient(base_url=settings.llm_base_url, headers=headers, timeout=settings.llm_timeout, transport=transport) as http:
        for _ in range(MAX_STEPS):
            resp = await http.post("/chat/completions", json={
                "model": settings.llm_model, "messages": messages, "tools": tools, "tool_choice": "auto", "temperature": 0})
            resp.raise_for_status()
            msg = resp.json()["choices"][0]["message"]
            messages.append(msg)
            if not msg.get("tool_calls"):
                if not run.calls:
                    # A model that answers without touching the graph has nothing to ground its words in.
                    raise ModelUnusable("the model answered without calling any tool, so its answer is not grounded in the graph")
                run.answer = (msg.get("content") or "").strip()
                return
            for tc in msg["tool_calls"]:
                args = _parse_args(tc["function"].get("arguments"))
                data = await call_tool(client, run, tc["function"]["name"], args)
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(data)[:12000]})
    run.answer = "The model did not finish within the step limit."


async def ask(question: str, at: str, settings: config.Settings | None = None,
              backend: str | None = None, transport: httpx.AsyncBaseTransport | None = None) -> AgentRun:
    settings = settings or config.load_settings()
    use_llm = (backend or ("llm" if settings.llm_configured else "planner")) == "llm"
    if use_llm and not settings.llm_configured:
        raise RuntimeError("LLM_BASE_URL and LLM_MODEL are not configured")
    run = AgentRun(question, at, "llm" if use_llm else "planner", settings.llm_model if use_llm else None)
    async with Client(build_server()) as client:
        if not use_llm:
            await run_planner(client, run)
            return run
        try:
            await run_llm(client, run, settings, transport)
        except (httpx.HTTPError, ModelUnusable, KeyError, IndexError, ValueError) as exc:
            # The model is optional. When it fails, answer with the planner and say so rather than error or bluff.
            reason = str(exc) or type(exc).__name__
            run = AgentRun(question, at, "planner", None, note=f"The model ({settings.llm_model}) could not be used: {reason}.")
            await run_planner(client, run)
    return run
