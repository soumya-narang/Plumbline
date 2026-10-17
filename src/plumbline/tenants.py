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

from plumbline.graph.client import connect, database, read_query_text, run_named
from plumbline.graph.loader import (
    load_advisory_list,
    load_advisory_rows,
    load_artifact_rows,
    load_lockgraph_rows,
)
from plumbline.graph.schema import apply_schema
from plumbline.graphdata import artifact_graph
from plumbline.ingest.lockgraph import rows_for
from plumbline.ingest.npm_lock import UnsupportedLockfile, parse_npm_lock, purl_for
from plumbline.snapshot import advisories_at
from plumbline.timeutil import now_ms, to_iso
from plumbline.triage.engine import triage_advisory
from plumbline.triage.serialize import verdict_view

PREFIX = "plumbline_t_"
TEMPLATE = "plumbline_template"
ARTIFACT_ID = "your/project"
MAX_BYTES = 4_000_000
MAX_PACKAGES = 8_000
MAX_EDGES = 20_000  # the largest real lockfile we have has under 5,000; a denser upload only costs everyone time
MAX_TENANTS = 25
MAX_PER_OWNER = 3
TTL_MS = 30 * 60 * 1000
MAX_EXTRA = 10
_ID = re.compile(r"^[0-9a-f]{32}$")
_NAME = re.compile(r"^(@[a-z0-9][a-z0-9._~-]{0,213}/)?[a-z0-9][a-z0-9._~-]{0,213}$")
_VERSION = re.compile(r"^\d{1,6}\.\d{1,6}\.\d{1,6}(-[0-9A-Za-z.-]{1,32})?(\+[0-9A-Za-z.-]{1,32})?$")

_lock = threading.Lock()  # guards the template, the capacity count and id reservation; never held while loading
_template_ready = False
_loading: dict[str, str] = {}  # id -> owner of graphs that exist but are still being filled; a sweep leaves them alone


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
    artifact, label, created_ms, owner, packages = rows[0]
    return {"artifact": artifact, "label": label, "created_ms": created_ms, "owner": owner, "packages": packages}


def sweep() -> int:
    """Delete tenant graphs older than the time limit. Returns how many were removed."""
    removed = 0
    for name in _tenant_names():
        if name.removeprefix(PREFIX) in _loading:
            continue
        info = _info(name)
        if info is None or now_ms() - (info["created_ms"] or 0) > TTL_MS:
            connect(name).delete()
            removed += 1
    return removed


def _minutes_until_free(infos: list[dict]) -> int:
    soonest = min((i["created_ms"] + TTL_MS for i in infos if i and i["created_ms"]), default=now_ms())
    return max(1, -(-(soonest - now_ms()) // 60_000))


def _validate(raw: bytes):
    if len(raw) > MAX_BYTES:
        raise TenantError(f"the lockfile is larger than {MAX_BYTES // 1_000_000} MB")
    try:
        parsed = parse_npm_lock(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TenantError("that is not valid JSON") from exc
    except RecursionError as exc:
        raise TenantError("that JSON is nested too deeply to be a lockfile") from exc
    except UnsupportedLockfile as exc:
        raise TenantError("only npm lockfiles (package-lock.json, lockfileVersion 2 or 3) can be read") from exc
    except (KeyError, TypeError, AttributeError) as exc:
        raise TenantError("that does not look like an npm lockfile") from exc
    third_party = [d for d in parsed.deps.values() if not d.workspace]
    if not third_party:
        raise TenantError("the lockfile lists no packages")
    if len(third_party) > MAX_PACKAGES:
        raise TenantError(f"the lockfile has more than {MAX_PACKAGES:,} packages")
    if len(parsed.edges) > MAX_EDGES:
        raise TenantError(f"the lockfile has more than {MAX_EDGES:,} dependency links, far beyond a real project")
    return parsed


def parse_extra(entries: list[str]) -> list[dict]:
    """Turn ``package@version`` lines into advisory rows, so a project can be checked against any list of bad versions."""
    by_package: dict[str, set[str]] = {}
    given = [e.strip() for e in entries if e.strip()]
    if len(given) > MAX_EXTRA:
        raise TenantError(f"at most {MAX_EXTRA} package versions can be checked at once")
    for entry in given:
        name, sep, version = entry.rpartition("@")
        if not sep or not name or not _NAME.match(name) or not _VERSION.match(version):
            raise TenantError(f'"{entry[:60]}" is not a package version; write it as package@version, for example left-pad@1.3.0')
        by_package.setdefault(name, set()).add(version)
    return [{
        "id": f"YOUR-LIST-{i}", "kind": "CUSTOM", "package": name, "summary": f"From your list: {name}",
        "published": "your list", "published_ms": 0,
        "affected": [{"name": name, "version": v, "purl": purl_for(name, v)} for v in sorted(versions)]}
        for i, (name, versions) in enumerate(sorted(by_package.items()), 1)]


def _reserve(owner: str, artifact: dict, label: str) -> tuple[str, Graph]:
    """Check the limits and create the graph with its artifact and stamp already in place, quickly, under the lock.

    The stamp must exist before the lock is released: FalkorDB panics (and takes every graph down with it) when a query
    returns a property that has never been set on that graph, and a concurrent upload's capacity check reads this one."""
    with _lock:
        ensure_template()
        sweep()
        names = _tenant_names()
        infos = [_info(n) for n in names]
        mine = [i for i in infos if i and owner and i["owner"] == owner]
        pending = sum(1 for o in _loading.values() if o == owner)
        if owner and len(mine) + pending >= MAX_PER_OWNER:
            raise TenantError(f"you already have {MAX_PER_OWNER} checks open; delete one or wait {_minutes_until_free(mine)} min")
        if len(names) >= MAX_TENANTS:
            raise TenantError(f"too many projects are being checked right now; try again in {_minutes_until_free(infos)} min")
        tenant_id = secrets.token_hex(16)
        graph = connect(TEMPLATE).copy(PREFIX + tenant_id)  # GRAPH.COPY: schema, indexes and advisories come along
        _loading[tenant_id] = owner
        try:
            load_artifact_rows(graph, [artifact])
            run_named(graph, "tenant/stamp", {"now_ms": now_ms(), "label": label, "owner": owner}, read_only=False)
        except Exception:
            _loading.pop(tenant_id, None)
            graph.delete()
            raise
        return tenant_id, graph


def create(raw: bytes, label: str = "", owner: str = "", extra: list[str] | None = None) -> dict:
    """Validate an upload, give it its own graph and return its first report.

    ``extra`` is an optional list of ``package@version`` strings to check as well as the incident's advisories."""
    parsed = _validate(raw)
    extra_rows = parse_extra(extra or [])
    label = re.sub(r"[^\w .@/-]", "", label)[:60] or "your project"
    tenant_id, graph = _reserve(owner, {
        "id": ARTIFACT_ID, "kind": "upload", "sha": None, "committed_at": None, "lockfile": "package-lock.json",
        "lock_state": "present", "lock_sha256": hashlib.sha256(raw).hexdigest(), "synthetic": False}, label)
    try:
        if extra_rows:
            load_advisory_list(graph, extra_rows)
        load_lockgraph_rows(graph, rows_for(ARTIFACT_ID, parsed))
    except Exception:
        graph.delete()  # never leave a half-filled graph holding a slot
        raise
    finally:
        _loading.pop(tenant_id, None)
    return report(tenant_id)


def _tenant(tenant_id: str) -> Graph:
    name = _graph_name(tenant_id)
    if name not in _tenant_names():
        raise TenantError("that check has expired or never existed")
    return connect(name)


# The queries that run for every check, in the order they run, so the page can show the graph's part of the work.
WORK = (
    ("triage/relevant_locks", "Find every install in the project that is the advisory's package or a version it names"),
    ("q2_explain_path", "Follow REQUIRES edges from a direct dependency to the poisoned install (shortest path)"),
    ("triage/via_direct", "Name the direct dependencies that lead there: what to bump"),
)


def _work(graph: Graph) -> dict:
    installs, requirements = run_named(graph, "tenant/size").result_set[0]
    return {
        "graph": {"installs": installs, "requirements": requirements},
        "queries": [{"name": n.split("/")[-1], "role": role, "cypher": read_query_text(n).strip()} for n, role in WORK],
    }


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
        "summary": summary, "findings": items, "work": _work(graph),
    }


def graph_payload(tenant_id: str) -> dict:
    return artifact_graph(_tenant(tenant_id), ARTIFACT_ID)


def delete(tenant_id: str) -> None:
    _tenant(tenant_id).delete()
