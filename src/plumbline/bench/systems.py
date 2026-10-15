"""Three ways to answer the same lockfile questions, all reading the same pinned facts.

* ``GraphSystem``      FalkorDB, one short Cypher query per question
* ``SqlSystem``        SQLite with a recursive query: the fair, strong alternative
* ``RetrievalSystem``  naive text retrieval over lockfile entries, with two retrieval rounds and no graph traversal

Each exposes ``locks``, ``pulled_by`` and ``fleet`` so the runner can grade them identically.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from collections import Counter, defaultdict

from falkordb import Graph

from plumbline.graph.client import read_query_text, run_named
from plumbline.ingest.fleet import FleetEntry
from plumbline.ingest.lockgraph import lockgraph_path


def load_facts(entries: list[FleetEntry]) -> tuple[list[tuple], list[tuple]]:
    """Dependency rows ``(artifact, key, name, version, direct)`` and edge rows ``(artifact, src, dst)``."""
    deps: list[tuple] = []
    edges: list[tuple] = []
    for e in entries:
        for line in lockgraph_path(e).read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r["t"] == "dep" and not r["workspace"]:
                deps.append((e.id, r["key"], r["name"], r["version"], int(r["direct"])))
            elif r["t"] == "requires":
                edges.append((e.id, r["from"].split("::", 1)[1], r["to"].split("::", 1)[1]))
    return deps, edges


def _count_lines(text: str, comment: str) -> int:
    return sum(1 for ln in text.splitlines() if ln.strip() and not ln.strip().startswith(comment))


class GraphSystem:
    name = "graph"

    def __init__(self, graph: Graph):
        self.graph = graph

    def locks(self, artifact: str, name: str, version: str) -> bool:
        rows = run_named(self.graph, "bench/locks", {"artifact": artifact, "name": name, "version": version}).result_set
        return bool(rows[0][0])

    def pulled_by(self, artifact: str, name: str, version: str) -> set[str]:
        rows = run_named(self.graph, "bench/pulled_by", {"artifact": artifact, "name": name, "version": version}).result_set
        return {r[0] for r in rows}

    def fleet(self, name: str, version: str) -> set[str]:
        return {r[0] for r in run_named(self.graph, "bench/fleet", {"name": name, "version": version}).result_set}

    @staticmethod
    def query_lines() -> dict[str, int]:
        return {k: _count_lines(read_query_text(f"bench/{k}"), "//") for k in ("locks", "pulled_by", "fleet")}


SQL_LOCKS = "SELECT 1 FROM dep WHERE artifact = ? AND name = ? AND version = ? LIMIT 1"
SQL_PULLED_BY = """
WITH RECURSIVE reach(top, node) AS (
  SELECT key, key FROM dep WHERE artifact = :a AND direct = 1
  UNION
  SELECT r.top, e.dst FROM reach r JOIN edge e ON e.artifact = :a AND e.src = r.node
)
SELECT DISTINCT d.name
FROM reach r
JOIN dep d ON d.artifact = :a AND d.key = r.top
WHERE r.node IN (SELECT key FROM dep WHERE artifact = :a AND name = :n AND version = :v)
ORDER BY d.name
"""
# The version an experienced engineer writes: walk upward from the target and keep the direct dependencies.
SQL_PULLED_BY_REVERSE = """
WITH RECURSIVE up(node) AS (
  SELECT key FROM dep WHERE artifact = :a AND name = :n AND version = :v
  UNION
  SELECT e.src FROM up JOIN edge e ON e.artifact = :a AND e.dst = up.node
)
SELECT DISTINCT d.name FROM up JOIN dep d ON d.artifact = :a AND d.key = up.node
WHERE d.direct = 1
ORDER BY d.name
"""
SQL_FLEET = "SELECT DISTINCT artifact FROM dep WHERE name = ? AND version = ? ORDER BY artifact"


class SqlSystem:
    """SQLite over the same facts. ``reverse`` is the tuned query; ``forward`` is the first, naive attempt."""

    def __init__(self, deps: list[tuple], edges: list[tuple], strategy: str = "reverse"):
        self.name = "sql" if strategy == "reverse" else "sql_forward"
        self.pulled_by_sql = SQL_PULLED_BY_REVERSE if strategy == "reverse" else SQL_PULLED_BY
        self.db = sqlite3.connect(":memory:")
        self.db.executescript(
            "CREATE TABLE dep (artifact TEXT, key TEXT, name TEXT, version TEXT, direct INTEGER);"
            "CREATE TABLE edge (artifact TEXT, src TEXT, dst TEXT);"
            "CREATE INDEX dep_nv ON dep (name, version);"
            "CREATE INDEX dep_ak ON dep (artifact, key);"
            "CREATE INDEX edge_as ON edge (artifact, src);")
        self.db.executemany("INSERT INTO dep VALUES (?, ?, ?, ?, ?)", deps)
        self.db.executemany("INSERT INTO edge VALUES (?, ?, ?)", edges)

    def locks(self, artifact: str, name: str, version: str) -> bool:
        return self.db.execute(SQL_LOCKS, (artifact, name, version)).fetchone() is not None

    def pulled_by(self, artifact: str, name: str, version: str) -> set[str]:
        return {r[0] for r in self.db.execute(self.pulled_by_sql, {"a": artifact, "n": name, "v": version})}

    def fleet(self, name: str, version: str) -> set[str]:
        return {r[0] for r in self.db.execute(SQL_FLEET, (name, version))}

    def query_lines(self) -> dict[str, int]:
        return {"locks": _count_lines(SQL_LOCKS, "--"), "pulled_by": _count_lines(self.pulled_by_sql, "--"),
                "fleet": _count_lines(SQL_FLEET, "--")}


_TOKEN = re.compile(r"\S+")


class RetrievalSystem:
    """A deliberately ordinary retrieval baseline: BM25 over one text chunk per locked package."""

    name = "retrieval"
    K = 20  # chunks returned per retrieval call
    ROUNDS = 2  # how many times it may retrieve again, following "requires" mentions

    def __init__(self, deps: list[tuple], edges: list[tuple]):
        names = {(a, k): n for a, k, n, _v, _d in deps}
        children: dict[tuple[str, str], set[str]] = defaultdict(set)
        for a, s, t in edges:
            children[(a, s)].add(names.get((a, t), ""))
        self.chunks = []
        for a, k, n, v, direct in deps:
            kids = children[(a, k)]
            text = f"{a} {n} {v} {'direct' if direct else ''} requires {' '.join(sorted(kids))}"
            self.chunks.append({"artifact": a, "name": n, "version": v, "direct": bool(direct), "requires": kids,
                                "tokens": [t.lower() for t in _TOKEN.findall(text)]})
        self.df: Counter = Counter()
        for c in self.chunks:
            self.df.update(set(c["tokens"]))
        self.avg = sum(len(c["tokens"]) for c in self.chunks) / max(1, len(self.chunks))

    def _search(self, query: str, k: int) -> list[dict]:
        terms = [t.lower() for t in _TOKEN.findall(query)]
        n = len(self.chunks)
        scored = []
        for c in self.chunks:
            tf = Counter(c["tokens"])
            score = 0.0
            for t in terms:
                if t in tf:
                    idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                    score += idf * tf[t] * 2.2 / (tf[t] + 1.2 * (0.25 + 0.75 * len(c["tokens"]) / self.avg))
            if score > 0:
                scored.append((score, c))
        scored.sort(key=lambda x: -x[0])
        return [c for _, c in scored[:k]]

    def locks(self, artifact: str, name: str, version: str) -> bool:
        top = self._search(f"{artifact} {name} {version}", 1)
        return bool(top) and (top[0]["artifact"], top[0]["name"], top[0]["version"]) == (artifact, name, version)

    def pulled_by(self, artifact: str, name: str, version: str) -> set[str]:
        hit = self._search(f"{artifact} {name} {version}", 1)
        if not hit or (hit[0]["artifact"], hit[0]["name"], hit[0]["version"]) != (artifact, name, version):
            return set()
        found: set[str] = {name} if hit[0]["direct"] else set()
        frontier = {name}
        for _ in range(self.ROUNDS):
            nxt: set[str] = set()
            for target in frontier:
                for c in self._search(f"{artifact} requires {target}", self.K):
                    if c["artifact"] == artifact and target in c["requires"]:
                        (found if c["direct"] else nxt).add(c["name"])
            frontier = nxt
        return found

    def fleet(self, name: str, version: str) -> set[str]:
        return {c["artifact"] for c in self._search(f"{name} {version}", 10) if (c["name"], c["version"]) == (name, version)}

    @staticmethod
    def query_lines() -> dict[str, int]:
        return {"locks": 0, "pulled_by": 0, "fleet": 0}
