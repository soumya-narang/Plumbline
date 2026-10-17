"""Bring your own lockfile: one isolated FalkorDB graph per upload.

A template graph holds the schema and the incident's advisories. Each upload gets its own graph, created from the
template with ``GRAPH.COPY``, so one visitor's dependencies are never visible to another, the shared fleet graph is
never touched, and the whole graph can be deleted when its time is up.

Only lockfile structure is read. Nothing in an upload is installed or executed.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading

from falkordb import Graph
from redis.exceptions import ResponseError

from plumbline.graph.client import connect, database, run_named
from plumbline.graph.loader import load_advisory_rows, load_artifact_rows, load_lockgraph_rows
from plumbline.graph.schema import apply_schema
from plumbline.graphdata import artifact_graph
from plumbline.ingest.lockgraph import rows_for
from plumbline.ingest.npm_lock import UnsupportedLockfile, parse_npm_lock
from plumbline.snapshot import advisories_at
from plumbline.timeutil import now_ms, to_iso
from plumbline.triage.engine import triage_advisory
from plumbline.triage.serialize import verdict_view

PREFIX = "plumbline_t_"
TEMPLATE = "plumbline_template"
ARTIFACT_ID = "your/project"
MAX_BYTES = 4_000_000
MAX_PACKAGES = 8_000
MAX_TENANTS = 25
TTL_MS = 2 * 60 * 60 * 1000
_ID = re.compile(r"^[0-9a-f]{8}$")

_lock = threading.Lock()
_template_ready = False


class TenantError(ValueError):
    """The upload cannot be used; the message says why and is safe to show."""


def _graph_name(tenant_id: str) -> str:
    if not _ID.match(tenant_id):
        raise TenantError("unknown tenant")
    return PREFIX + tenant_id


def ensure_template() -> None:
    """(Re)build the template graph once per process, so it always carries the current advisories."""
    global _template_ready
    if _template_ready:
        return
    graph = connect(TEMPLATE)
    try:
        graph.delete()
    except ResponseError:
        pass
    apply_schema(graph)
    load_advisory_rows(graph)
    _template_ready = True


def _tenant_names() -> list[str]:
    return [g for g in database().list_graphs() if g.startswith(PREFIX)]


def _info(name: str) -> dict | None:
    rows = run_named(connect(name), "tenant/info").result_set
    if not rows:
        return None
    artifact, label, created_ms, packages = rows[0]
    return {"artifact": artifact, "label": label, "created_ms": created_ms, "packages": packages}


def sweep() -> int:
    """Delete tenant graphs older than the time limit. Returns how many were removed."""
    removed = 0
    for name in _tenant_names():
        info = _info(name)
        if info is None or now_ms() - (info["created_ms"] or 0) > TTL_MS:
            connect(name).delete()
            removed += 1
    return removed


def _validate(raw: bytes):
    if len(raw) > MAX_BYTES:
        raise TenantError(f"the lockfile is larger than {MAX_BYTES // 1_000_000} MB")
    try:
        parsed = parse_npm_lock(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TenantError("that is not valid JSON") from exc
    except UnsupportedLockfile as exc:
        raise TenantError("only npm lockfiles (package-lock.json, lockfileVersion 2 or 3) can be read") from exc
    except (KeyError, TypeError, AttributeError) as exc:
        raise TenantError("that does not look like an npm lockfile") from exc
    third_party = [d for d in parsed.deps.values() if not d.workspace]
    if not third_party:
        raise TenantError("the lockfile lists no packages")
    if len(third_party) > MAX_PACKAGES:
        raise TenantError(f"the lockfile has more than {MAX_PACKAGES:,} packages")
    return parsed


def create(raw: bytes, label: str = "") -> dict:
    """Validate an upload, give it its own graph and return its first report."""
    parsed = _validate(raw)
    label = re.sub(r"[^\w .@/-]", "", label)[:60] or "your project"
    with _lock:
        ensure_template()
        sweep()
        if len(_tenant_names()) >= MAX_TENANTS:
            raise TenantError("too many projects are being checked right now; try again in a few minutes")
        tenant_id = secrets.token_hex(4)
        graph = connect(TEMPLATE).copy(PREFIX + tenant_id)  # GRAPH.COPY: schema, indexes and advisories come along
        load_artifact_rows(graph, [{
            "id": ARTIFACT_ID, "kind": "upload", "sha": None, "committed_at": None, "lockfile": "package-lock.json",
            "lock_state": "present", "lock_sha256": hashlib.sha256(raw).hexdigest(), "synthetic": False}])
        load_lockgraph_rows(graph, rows_for(ARTIFACT_ID, parsed))
        run_named(graph, "tenant/stamp", {"now_ms": now_ms(), "label": label}, read_only=False)
    return report(tenant_id)


def _tenant(tenant_id: str) -> Graph:
    name = _graph_name(tenant_id)
    if name not in _tenant_names():
        raise TenantError("that check has expired or never existed")
    return connect(name)


def report(tenant_id: str) -> dict:
    graph = _tenant(tenant_id)
    info = _info(PREFIX + tenant_id)
    at = now_ms()
    items = []
    summary = {"EXPOSED": 0, "CLEARED": 0, "UNKNOWN": 0}
    for adv in advisories_at(graph, at):
        verdict = triage_advisory(graph, adv["id"], at).verdicts[0]
        row = verdict_view(adv["id"], at, verdict)
        summary[row["verdict"]] += 1
        items.append({"advisory": adv["id"], "package": adv["package"], "published": adv["published"], **row})
    return {
        "tenant": tenant_id, "label": info["label"], "artifact": ARTIFACT_ID, "packages": info["packages"],
        "created": to_iso(info["created_ms"]), "expires": to_iso(info["created_ms"] + TTL_MS),
        "summary": summary, "findings": items,
    }


def graph_payload(tenant_id: str) -> dict:
    return artifact_graph(_tenant(tenant_id), ARTIFACT_ID)


def delete(tenant_id: str) -> None:
    _tenant(tenant_id).delete()
