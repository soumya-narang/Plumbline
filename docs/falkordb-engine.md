# FalkorDB engine: verified behaviour

Recorded on 2026-10-15 against the local container started by `docker-compose.yml`.
Everything marked **verified** was run, not read from documentation.

## Environment

| Item | Value |
|---|---|
| Image | `falkordb/falkordb@sha256:b0bdcac2cbaff989e77cb0610439b7a9289e86de033ccbbd4368b66fb680ae7a` (all 227 tests pass against it; the id recorded on 2026-10-15 was `sha256:1074...59ba6`, an earlier build of `latest`) |
| `graph` module version | `60002` (from `MODULE LIST`) |
| Host ports | `6390` (database), `3010` (browser); `6379` is taken by another Redis on the dev machine |

The image is pinned by digest in `Dockerfile` and `docker-compose.yml`.
Which engine implementation (C or the Rust preview) this image runs is **not established**; make no claim about it.

## Procedures (verified via `CALL dbms.procedures()`)

Algorithms: `algo.BFS`, `algo.HarmonicCentrality`, `algo.MSF`, `algo.SPpaths`, `algo.SSpaths`, `algo.WCC`,
`algo.betweenness`, `algo.labelPropagation`, `algo.maxFlow`, `algo.pageRank`.
Indexes and schema: `db.constraints`, `db.indexes`, `db.labels`, `db.propertyKeys`, `db.relationshipTypes`, `db.meta.stats`,
`db.idx.fulltext.createNodeIndex`, `db.idx.fulltext.drop`, `db.idx.fulltext.queryNodes`, `db.idx.fulltext.queryRelationships`,
`db.idx.vector.queryNodes`, `db.idx.vector.queryRelationships`.
Introspection: `dbms.functions`, `dbms.procedures`.

Spelling matters: `algo.BFS` and `algo.SPpaths` are capitalised; `algo.pageRank` and `algo.betweenness` are not.

## Cypher forms the project relies on

| Form | Result | Note |
|---|---|---|
| `MATCH p = shortestPath(...)` | **Rejected** | `shortestPath` is only allowed in `WITH` or `RETURN` |
| `WITH a, b, shortestPath((a)-[:R*0..8]->(b)) AS p RETURN ...` | Works | Use `*0..N` so a direct dependency yields length 0 |
| Unreachable pair | `p IS NULL` is true | Handle explicitly; this is the "no path" case |
| `-[:R*0..2]->` lower bound 0 | Works | |
| `WHERE NOT (d)-[:R]->(:L)` | Works | |
| `WHERE f.id IN [...]` | Works | |
| `CALL algo.pageRank('Label','REL') YIELD node, score` | Works under `GRAPH.RO_QUERY` | |
| `CALL algo.betweenness({nodeLabels, relationshipTypes, samplingSize, samplingSeed})` | Works | Fixed seed gives reproducible output |
| `GRAPH.COPY src dest` | Works | Used for per-tenant graphs |
| `GRAPH.EXPLAIN` | Works | Returns the execution plan text |
| `GRAPH.CONSTRAINT CREATE ... UNIQUE` | Fails without an exact-match index | Create the index first |

## Open items

- Cost and memory overhead of `GRAPH.COPY` for the full fleet graph: measure when the loader exists.
- `GRAPH.PROFILE` and `GRAPH.SLOWLOG`: not tried.
- Whether `algo.SPpaths` is needed at all (it is a COULD-tier tool).
