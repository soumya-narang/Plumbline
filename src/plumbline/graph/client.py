"""FalkorDB connection and named-query helpers."""

from __future__ import annotations

from falkordb import FalkorDB, Graph

from plumbline import config

DEFAULT_GRAPH = "plumbline"


def database() -> FalkorDB:
    s = config.load_settings()
    return FalkorDB(host=s.falkordb_host, port=s.falkordb_port, password=s.falkordb_password)


def connect(graph_name: str = DEFAULT_GRAPH) -> Graph:
    return database().select_graph(graph_name)


def read_query_text(name: str) -> str:
    """Return the text of ``queries/<name>.cypher`` (``name`` may include a subfolder, e.g. ``load/requires``)."""
    return (config.QUERIES / f"{name}.cypher").read_text(encoding="utf-8")


def run_named(graph: Graph, name: str, params: dict | None = None, read_only: bool = True):
    text = read_query_text(name)
    return graph.ro_query(text, params or {}) if read_only else graph.query(text, params or {})
