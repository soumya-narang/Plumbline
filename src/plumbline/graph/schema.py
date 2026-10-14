"""Indexes and constraints. Constraints require an exact-match index to exist first."""

from __future__ import annotations

from falkordb import Graph

# (label, property) pairs that are looked up by value during loading and querying.
INDEXED = [
    ("Artifact", "id"),
    ("Advisory", "id"),
    ("PackageVersion", "purl"),
    ("LockedDep", "id"),
    ("Service", "id"),
    ("Exposure", "id"),
]
UNIQUE = [("Artifact", "id"), ("Advisory", "id"), ("PackageVersion", "purl"), ("LockedDep", "id")]


def apply_schema(graph: Graph) -> None:
    for label, prop in INDEXED:
        graph.create_node_range_index(label, prop)
    for label, prop in UNIQUE:
        graph.create_node_unique_constraint(label, prop)
