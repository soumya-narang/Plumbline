"""HTTP API and static UI.

Replaying mutates the graph (it wipes and rewrites decision memory), so every operation that touches memory runs
under one lock, and snapshots are cached per timestamp.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import threading
import time

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from plumbline import config, tenants
from plumbline.agent.runner import ask
from plumbline.api.sessions import COOKIE, Approvals, Refused, clean_name
from plumbline.graph.client import connect
from plumbline.graphdata import artifact_graph
from plumbline.memory import tasks
from plumbline.memory.decisions import propose
from plumbline.memory.replay import seek
from plumbline.snapshot import advisories_at, build_meta, snapshot
from plumbline.timeutil import to_iso, to_ms
from plumbline.triage.engine import triage_artifact
from plumbline.triage.receipt import make_receipt, verify

WEB_DIR = config.ROOT / "web"
LLM_MAX_PER_HOUR = int(os.getenv("LLM_MAX_ASKS_PER_HOUR", "60"))

# No script runs unless it is a file served from here. Inline styles are allowed because the UI sets CSS variables
# per element. The page may be framed only by itself and by Hugging Face, which embeds Spaces.
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
        "frame-ancestors 'self' https://huggingface.co https://*.hf.space"),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), interest-cohort=()",
}

_lock = threading.RLock()
_cache: dict[tuple[int, str], dict] = {}
CACHE_LIMIT = 400
approvals = Approvals(enabled=os.getenv("PLUMBLINE_APPROVALS", "on") != "off")
_llm_calls: list[float] = []


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    at: str


class ApproveBody(BaseModel):
    advisory: str
    artifact: str
    at: str
    approver: str = Field(min_length=1, max_length=80)


class ReviseBody(BaseModel):
    advisory: str
    version: str = Field(pattern=r"^\d{1,6}\.\d{1,6}\.\d{1,6}(-[0-9A-Za-z.]{1,24})?$")
    at: str


class CheckBody(BaseModel):
    lockfile: str = Field(min_length=2, max_length=4_100_000)
    label: str = Field(default="", max_length=80)
    extra: list[str] = Field(default_factory=list, max_length=20)  # package@version entries to check as well


class VerifyBody(BaseModel):
    payload: dict
    hash: str


def _client_id(request: Request) -> str:
    """A short, non-reversible id for the caller, used to share limits fairly. Behind a trusted proxy the real client
    address is the first entry of X-Forwarded-For; otherwise it is the socket's peer."""
    forwarded = request.headers.get("x-forwarded-for", "")
    host = forwarded.split(",")[0].strip() if forwarded and os.getenv("PLUMBLINE_TRUST_PROXY") == "1" else ""
    host = host or (request.client.host if request.client else "unknown")
    return hashlib.sha256(host.encode()).hexdigest()[:12]


def _session(request: Request, response: Response) -> str:
    """The visitor's session id from its cookie, issuing one on first contact."""
    sid = request.cookies.get(COOKIE)
    if not sid or len(sid) != 32 or not all(c in "0123456789abcdef" for c in sid):
        sid = approvals.new_session()
        secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
        response.set_cookie(COOKIE, sid, max_age=86_400, httponly=True, samesite="lax", secure=secure)
    return sid


def _remember(key: tuple[int, str], snap: dict) -> dict:
    if len(_cache) >= CACHE_LIMIT:
        _cache.clear()
    _cache[key] = snap
    return snap


def _snapshot(at_ms: int, sid: str) -> dict:
    with _lock:
        history = approvals.history(sid)
        key = (at_ms, approvals.digest(sid))
        if key not in _cache:
            return _remember(key, snapshot(connect(), at_ms, history))
        seek(connect(), at_ms, history)  # keep the graph's memory aligned with the cursor the caller is about to read
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
    app = FastAPI(title="Plumbline", docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")

    @app.middleware("http")
    async def harden_responses(request, call_next):
        """Security headers on everything; and pages and scripts are revalidated, because browsers otherwise keep
        serving old copies after an update."""
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        path = request.url.path
        if not path.startswith("/api/") and not path.startswith("/fonts/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/api/health")
    def health() -> dict:
        n = connect().ro_query("MATCH (a:Artifact) RETURN count(a)").result_set[0][0]
        return {"ok": n > 0, "artifacts": n}

    @app.get("/api/meta")
    def meta() -> dict:
        settings = config.load_settings()
        return {
            **build_meta(connect()),
            "mode": "live",
            "agent": {"backend": "llm" if settings.llm_configured else "planner",
                      "model": settings.llm_model if settings.llm_configured else None},
        }

    @app.get("/api/snapshot")
    def get_snapshot(at: str, request: Request, response: Response) -> dict:
        return _snapshot(_parse_at(at), _session(request, response))

    @app.post("/api/ask")
    async def post_ask(body: AskBody, request: Request, response: Response) -> dict:
        at_ms = _parse_at(body.at)
        history = approvals.history(_session(request, response))
        settings = config.load_settings()
        backend = "llm" if settings.llm_configured and _llm_allowed() else "planner"

        def work() -> dict:
            with _lock:
                seek(connect(), at_ms, history)
                return asyncio.run(ask(body.question, to_iso(at_ms), settings, backend)).to_dict()

        return await asyncio.to_thread(work)

    @app.post("/api/approve")
    def approve(body: ApproveBody, request: Request, response: Response) -> dict:
        at_ms = _parse_at(body.at)
        sid, client = _session(request, response), _client_id(request)
        try:
            approver = clean_name(body.approver)
            approvals.check_allowed(sid, client)
        except Refused as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        with _lock:
            seek(connect(), at_ms, approvals.history(sid))
            try:
                proposal = propose(connect(), body.advisory, body.artifact, at_ms)
            except LookupError as exc:
                raise HTTPException(404, str(exc)) from exc
            approvals.add(sid, client, {"at": to_iso(at_ms), "type": "approve", "advisory": body.advisory,
                                        "artifact": body.artifact, "approver": approver, "manual": True})
            snap = snapshot(connect(), at_ms, approvals.history(sid))
            _remember((at_ms, approvals.digest(sid)), snap)
            return {"decision": proposal.decision_id, "snapshot": snap}

    @app.post("/api/revise")
    def revise(body: ReviseBody, request: Request, response: Response) -> dict:
        """A what-if that belongs to this visitor: suppose the advisory also named this version, as of this moment.
        It is replayed for this visitor only and is labelled hypothetical everywhere it is shown."""
        at_ms = _parse_at(body.at)
        sid, client = _session(request, response), _client_id(request)
        try:
            approvals.check_allowed(sid, client)
        except Refused as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        with _lock:
            advisory = next((a for a in advisories_at(connect(), at_ms) if a["id"] == body.advisory), None)
            if advisory is None:
                raise HTTPException(404, f"{body.advisory} is not published at {body.at}")
            purl = f"pkg:npm/{advisory['package']}@{body.version}"
            known = {p for a in snapshot(connect(), at_ms, approvals.history(sid))["advisories"]
                     if a["id"] == body.advisory for p in a["affected_purls"]}
            if purl in known:
                raise HTTPException(422, f"{advisory['package']}@{body.version} is already named by {body.advisory}")
            approvals.add(sid, client, {
                "at": to_iso(at_ms), "type": "advisory_revised", "scripted": True, "visitor": True, "advisory": body.advisory,
                "add_purls": [purl], "note": "Added by you as a what-if. No real advisory names this version."})
            snap = snapshot(connect(), at_ms, approvals.history(sid))
            _remember((at_ms, approvals.digest(sid)), snap)
            return {"snapshot": snap}

    @app.delete("/api/revise")
    def clear_revisions(request: Request, response: Response) -> dict:
        """Forget this visitor's what-ifs (and approvals), returning them to the recorded incident."""
        approvals.clear(_session(request, response))
        return {"cleared": True}

    @app.get("/api/tasks")
    def get_tasks(status: str = "") -> dict:
        """The shared work queue the agents pass fixes through (read-only here)."""
        try:
            return {"tasks": tasks.list_tasks(connect(), status)}
        except tasks.WorkError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/check")
    def post_check(body: CheckBody, request: Request) -> dict:
        """Check your own lockfile: it gets its own graph and is judged against the incident's advisories."""
        try:
            return tenants.create(body.lockfile.encode("utf-8"), body.label, _client_id(request), [e[:120] for e in body.extra])
        except tenants.TenantError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/check/{tenant_id}")
    def get_check(tenant_id: str) -> dict:
        try:
            return tenants.report(tenant_id)
        except tenants.TenantError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/check/{tenant_id}/graph")
    def get_check_graph(tenant_id: str) -> dict:
        try:
            return tenants.graph_payload(tenant_id)
        except tenants.TenantError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.delete("/api/check/{tenant_id}")
    def delete_check(tenant_id: str) -> dict:
        try:
            tenants.delete(tenant_id)
        except tenants.TenantError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"deleted": True}

    @app.get("/api/graph")
    def get_graph(artifact: str) -> dict:
        data = artifact_graph(connect(), artifact)
        if not data["nodes"]:
            raise HTTPException(404, "no dependency graph for that artifact (it has no parsed lockfile)")
        return data

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
        @app.api_route("/", methods=["GET", "HEAD"])
        def index() -> FileResponse:
            return FileResponse(WEB_DIR / "index.html")

        app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
    return app


app = create_app()
