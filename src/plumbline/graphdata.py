"""One artifact's dependency graph in a compact form for the UI's graph view.

Nodes are arrays ``[key, name, version, depth, direct]`` and edges are ``[source_index, target_index]`` pairs, so a
2,000-package lockfile stays small enough to ship as static JSON.
"""

from __future__ import annotations

from falkordb import Graph

from plumbline.graph.client import run_named


def artifact_graph(graph: Graph, artifact: str) -> dict:
    nodes = run_named(graph, "graph/artifact_nodes", {"artifact": artifact}).result_set
    index = {row[0]: i for i, row in enumerate(nodes)}
    edges = [
        [index[s], index[t]]
        for s, t in run_named(graph, "graph/artifact_edges", {"artifact": artifact}).result_set
        if s in index and t in index
    ]
    return {"artifact": artifact, "nodes": [list(n) for n in nodes], "edges": sorted(edges)}
