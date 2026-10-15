"""Parse an npm lockfile (v2 or v3) into a resolved dependency graph.

npm's ``packages`` map is keyed by install path (``node_modules/a/node_modules/b``). A package's
``dependencies`` are names, not keys, so each name is resolved the way Node does it: look inside
the package's own ``node_modules``, then walk up the tree to the root.

Only lockfile *structure* is read. Nothing here installs or executes package code.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from urllib.parse import quote, unquote

ROOT_KEY = ""
HARD_FIELDS = ("dependencies", "optionalDependencies")


class UnsupportedLockfile(ValueError):
    """The lockfile is not an npm v2/v3 lockfile with a ``packages`` map."""


@dataclass(frozen=True)
class LockedDep:
    key: str  # install path inside the lockfile, e.g. "node_modules/a/node_modules/b"
    name: str
    version: str
    purl: str
    direct: bool  # required by the root package or by a workspace member
    dev: bool
    optional: bool
    workspace: bool  # first-party workspace member, not a third-party dependency
    depth: int | None  # minimum hops from a direct dependency; 1 for direct, None if unreachable


@dataclass
class LockGraph:
    deps: dict[str, LockedDep] = field(default_factory=dict)
    edges: list[tuple[str, str]] = field(default_factory=list)  # (from_key, to_key)


def purl_for(name: str, version: str) -> str:
    """Package URL for an npm package; the scope separator ``@`` is percent-encoded per the spec."""
    return f"pkg:npm/{quote(name, safe='/')}@{version}"


def _name_from_key(key: str) -> str:
    return key.rsplit("node_modules/", 1)[-1]


def _parent_prefix(prefix: str) -> str:
    """Prefix one ``node_modules`` level up: ``a/node_modules/b`` -> ``a``; no level left -> ``""``."""
    idx = prefix.rfind("node_modules/")
    return prefix[:idx].rstrip("/") if idx > 0 else ROOT_KEY


def _resolve(packages: dict, from_key: str, dep_name: str) -> str | None:
    """Return the lockfile key that ``dep_name`` resolves to when required from ``from_key``."""
    prefix = from_key
    while True:
        cand = f"{prefix}/node_modules/{dep_name}" if prefix else f"node_modules/{dep_name}"
        entry = packages.get(cand)
        if entry is not None:
            # A "link" entry points at a workspace member; follow it to the real key.
            return entry["resolved"] if entry.get("link") and entry.get("resolved") in packages else cand
        if not prefix:
            return None
        prefix = _parent_prefix(prefix)


def parse_npm_lock(raw: str | bytes) -> LockGraph:
    doc = json.loads(raw)
    packages = doc.get("packages")
    if not isinstance(packages, dict) or ROOT_KEY not in packages:
        raise UnsupportedLockfile(f"lockfileVersion {doc.get('lockfileVersion')!r} has no packages map")

    root = packages[ROOT_KEY]
    workspace_keys = {
        k for k, v in packages.items()
        if k and not v.get("link") and "node_modules" not in k.split("/")
    }
    dev_names = set(root.get("devDependencies") or {})

    graph = LockGraph()
    direct_keys: set[str] = set()

    def requires(key: str, meta: dict) -> set[str]:
        """The installs a package causes. A peer requirement only asks the host to provide a package, so it counts
        only when the lockfile marks the target as installed because of a peer (``"peer": true``); otherwise a
        package that merely has a peer dependency on X would wrongly appear to pull in everything X requires."""
        names: set[str] = set()
        for f in HARD_FIELDS:
            names.update(meta.get(f) or {})
        if key == ROOT_KEY:
            names.update(meta.get("devDependencies") or {})
            names.update(meta.get("peerDependencies") or {})
        resolved = {_resolve(packages, key, n) for n in names}
        for peer_name in meta.get("peerDependencies") or {}:
            target = _resolve(packages, key, peer_name)
            if target is not None and packages[target].get("peer"):
                resolved.add(target)
        resolved.discard(None)
        return resolved  # type: ignore[return-value]

    # Roots of the traversal: the root package and every workspace member.
    for src in {ROOT_KEY, *workspace_keys}:
        for dst in requires(src, packages[src]):
            direct_keys.add(dst)

    for key, meta in packages.items():
        if key == ROOT_KEY or meta.get("link"):
            continue
        name = meta.get("name") or _name_from_key(key)
        is_workspace = key in workspace_keys
        version = meta.get("version", "")
        graph.deps[key] = LockedDep(
            key=key,
            name=name,
            version=version,
            purl=purl_for(name, version),
            direct=key in direct_keys,
            dev=bool(meta.get("dev")) or (key in direct_keys and name in dev_names),
            optional=bool(meta.get("optional")),
            workspace=is_workspace,
            depth=None,
        )
        for dst in requires(key, meta):
            if dst != key:
                graph.edges.append((key, dst))

    graph.edges = sorted(set(graph.edges))
    _assign_depth(graph, direct_keys)
    return graph


def _assign_depth(graph: LockGraph, direct_keys: set[str]) -> None:
    out: dict[str, list[str]] = {}
    for a, b in graph.edges:
        out.setdefault(a, []).append(b)

    depth: dict[str, int] = {k: 1 for k in direct_keys if k in graph.deps}
    queue = deque(depth)
    while queue:
        cur = queue.popleft()
        for nxt in out.get(cur, ()):
            if nxt not in depth:
                depth[nxt] = depth[cur] + 1
                queue.append(nxt)

    for key, dep in list(graph.deps.items()):
        d = 0 if dep.workspace else depth.get(key)
        graph.deps[key] = LockedDep(**{**dep.__dict__, "depth": d})


def parse_purl(purl: str) -> tuple[str, str]:
    """Inverse of :func:`purl_for`: ``pkg:npm/%40scope/name@1.2.3`` -> ``("@scope/name", "1.2.3")``."""
    name, _, version = unquote(purl.removeprefix("pkg:npm/")).rpartition("@")
    return name, version
