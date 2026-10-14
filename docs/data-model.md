# Graph data model (as loaded today)

Design rule: the graph holds facts and evidence; verdict policy lives in code, not in the graph.
Everything below is produced by `python -m plumbline load` from the JSONL under `data/processed/`.

## Nodes

| Label | Key | Other properties | Source |
|---|---|---|---|
| `Artifact` | `id` (`owner/repo` or `planted/<name>`) | `kind`, `sha`, `committed_at`, `lockfile`, `lock_state`, `synthetic` | `data/fleet.json` |
| `LockedDep` | `id` (`<artifact>::<lockfile key>`) | `key`, `direct`, `dev`, `optional`, `workspace`, `depth` | parsed lockfile |
| `PackageVersion` | `purl` | `name`, `version`, `ecosystem` | lockfiles and advisories |
| `Advisory` | `id` (OSV id) | `kind`, `package`, `summary`, `published`, `published_ms` | OSV |
| `Service` | `id` (`svc:<name>`) | `name`, `tier`, `declared` | `data/overlay.json` (declared) |
| `Exposure` | `id` (`exp:<service>`) | `kind` (`internet` or `internal`), `declared` | `data/overlay.json` (declared) |

`LockedDep` is a per-artifact resolution node: the same package version locked by two artifacts has two
`LockedDep` nodes, so a path query never needs a per-artifact edge filter. First-party workspace members are
`LockedDep` nodes with `workspace = true` and no `IS` edge.

## Relationships

| Edge | Meaning |
|---|---|
| `(Artifact)-[:LOCKS]->(LockedDep)` | The artifact's lockfile contains this install |
| `(LockedDep)-[:REQUIRES]->(LockedDep)` | Resolved dependency, using Node's lookup (nested `node_modules` first, then up the tree) |
| `(LockedDep)-[:IS]->(PackageVersion)` | Which concrete package version the install is |
| `(Advisory)-[:AFFECTS]->(PackageVersion)` | Malicious or vulnerable version named by the advisory |
| `(Service)-[:RUNS]->(Artifact)` | Declared deployment |
| `(Service)-[:EXPOSED_VIA]->(Exposure)` | Declared exposure |

## Indexes and constraints

Range indexes on `Artifact.id`, `Advisory.id`, `PackageVersion.purl`, `LockedDep.id`, `Service.id`, `Exposure.id`.
Unique constraints on the first four.

## Not yet modelled

`Decision`, `Evidence`, `Receipt`, `Team`, tenants. They arrive with the verdict engine and decision memory.

## Honest limits

- Only npm lockfile v2 and v3 are parsed. Yarn and pnpm lockfiles produce `lock_state = unsupported`; repositories without a lockfile produce `absent`.
- The deployment overlay is a modelling assumption, not discovered data.
- Planted artifacts are hand-authored fixtures and are labelled `synthetic`.
