"""HTTP API and static UI.

Replaying mutates the graph (it wipes and rewrites decision memory), so every operation that touches memory runs
under one lock, and snapshots are cached per timestamp.
"""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from plumbline import config
from plumbline.agent.runner import ask
from plumbline.graph.client import connect
from plumbline.ingest.fleet import load_incident
from plumbline.memory.decisions import propose
from plumbline.memory.replay import seek
from plumbline.snapshot import snapshot, timeline
from plumbline.timeutil import to_iso, to_ms
from plumbline.triage.engine import triage_artifact
from plumbline.triage.receipt import make_receipt, verify

WEB_DIR = config.ROOT / "web"
LLM_MAX_PER_HOUR = int(__import__("os").getenv("LLM_MAX_ASKS_PER_HOUR", "60"))

_lock = threading.RLock()
_cache: dict[tuple[int, int], dict] = {}
_manual: list[dict] = []  # manual approvals, re-applied by every replay
_llm_calls: list[float] = []


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    at: str


class ApproveBody(BaseModel):
    advisory: str
    artifact: str
    at: str
    approver: str = Field(min_length=1, max_length=80)


class VerifyBody(BaseModel):
    payload: dict
    hash: str


def _snapshot(at_ms: int) -> dict:
    with _lock:
        key = (at_ms, len(_manual))
        if key not in _cache:
            _cache[key] = snapshot(connect(), at_ms, list(_manual))
        else:  # keep the graph's memory aligned with the cursor the caller is about to read
            seek(connect(), at_ms, list(_manual))
        return _cache[key]


def _parse_at(at: str) -> int:
    try:
        return to_ms(at)
    except ValueError as exc:
        raise HTTPException(422, f"invalid timestamp: {at!r}") from exc


def _llm_allowed() -> bool:
    now = time.time()
    _llm_calls[:] = [t for t in _llm_calls if now - t < 3600]
    if len(_llm_calls) >= LLM_MAX_PER_HOUR:
        return False
    _llm_calls.append(now)
    return True


def create_app() -> FastAPI:
    app = FastAPI(title="Plumbline", docs_url="/api/docs", openapi_url="/api/openapi.json")

    @app.get("/api/health")
    def health() -> dict:
        n = connect().ro_query("MATCH (a:Artifact) RETURN count(a)").result_set[0][0]
        return {"ok": n > 0, "artifacts": n}

    @app.get("/api/meta")
    def meta() -> dict:
        settings = config.load_settings()
        return {
            "mode": "live",
            "incident": load_incident(),
            "timeline": timeline(connect()),
            "agent": {"backend": "llm" if settings.llm_configured else "planner",
                      "model": settings.llm_model if settings.llm_configured else None},
        }

    @app.get("/api/snapshot")
    def get_snapshot(at: str) -> dict:
        return _snapshot(_parse_at(at))

    @app.post("/api/ask")
    async def post_ask(body: AskBody) -> dict:
        at_ms = _parse_at(body.at)
        settings = config.load_settings()
        backend = "llm" if settings.llm_configured and _llm_allowed() else "planner"

        def work() -> dict:
            with _lock:
                seek(connect(), at_ms, list(_manual))
                return asyncio.run(ask(body.question, to_iso(at_ms), settings, backend)).to_dict()

        return await asyncio.to_thread(work)

    @app.post("/api/approve")
    def approve(body: ApproveBody) -> dict:
        at_ms = _parse_at(body.at)
        with _lock:
            seek(connect(), at_ms, list(_manual))
            try:
                proposal = propose(connect(), body.advisory, body.artifact, at_ms)
            except LookupError as exc:
                raise HTTPException(404, str(exc)) from exc
            _manual.append({"at": to_iso(at_ms), "type": "approve", "advisory": body.advisory,
                            "artifact": body.artifact, "approver": body.approver, "manual": True})
            snap = snapshot(connect(), at_ms, list(_manual))
            _cache[(at_ms, len(_manual))] = snap
            return {"decision": proposal.decision_id, "snapshot": snap}

    @app.get("/api/receipt")
    def get_receipt(advisory: str, artifact: str, at: str) -> dict:
        at_ms = _parse_at(at)
        v = triage_artifact(connect(), advisory, artifact, at_ms)
        if v is None:
            raise HTTPException(404, "no verdict for that advisory and artifact at that time")
        return make_receipt(advisory, at_ms, v)

    @app.post("/api/verify")
    def post_verify(body: VerifyBody) -> dict:
        try:
            ok, detail = verify(connect(), {"payload": body.payload, "hash": body.hash})
        except (KeyError, ValueError) as exc:
            return {"ok": False, "detail": f"malformed receipt: {exc}"}
        return {"ok": ok, "detail": detail}

    if WEB_DIR.exists():
        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(WEB_DIR / "index.html")

        app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
    return app


app = create_app()
