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
| `Decision` | `id` (`dec:<advisory>:<artifact>@<ms>`) | `verdict`, `reason`, `action`, `status` (`accepted` or `reopened`), `created_ms`, `reopened_ms`, `approver`, `policy_version` | written on approval |
| `Fact` | `id` (`<kind>:<key>`) | `kind` (`lock_snapshot` or `not_affected`), `key`, `created_ms`, `superseded_ms` | created with the first decision that assumes it |
| `Receipt` | `hash` | `payload` (JSON) | written with each decision |

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
| `(Decision)-[:ABOUT]->(Advisory)`, `(Decision)-[:FOR]->(Artifact)` | What the decision concerns |
| `(Decision)-[:ASSUMES]->(Fact)` | The facts the decision rests on; the heart of the Reopen |
| `(Receipt)-[:PROVES]->(Decision)` | The hash-checked record of how the verdict was derived |

## Indexes and constraints

Range indexes on `Artifact.id`, `Advisory.id`, `PackageVersion.purl`, `LockedDep.id`, `Service.id`, `Exposure.id`.
Unique constraints on the first four.

## Assumptions and the Reopen

A decision records the facts it rests on as `ASSUMES` edges:

- `lock_snapshot:<hash>`: the lockfile the verdict was derived from (every decision has one).
- `not_affected:<advisory>:<purl>`: for each version of the advisory's package that the artifact locks, that the
  advisory does not name it. A CLEARED decision carries one per locked version.

When a later event contradicts a fact, the fact gets `superseded_ms` and query Q5 (`queries/q5_reopen_check.cypher`)
returns exactly the accepted decisions that assumed it. Those are marked `reopened` and re-evaluated.

## Time

Everything is evaluated *as of* a timestamp. An advisory is invisible before its `published_ms`, and a version added by
a later revision is invisible before the edge's `since_ms`. That is what lets the replay move backwards as well as forwards.

## Not yet modelled

`Team` (code owners), tenants, `Task` handoff and `Playbook` (procedural memory).

## Honest limits

- Only npm lockfile v2 and v3 are parsed. Yarn and pnpm lockfiles produce `lock_state = unsupported`; repositories without a lockfile produce `absent`.
- The deployment overlay is a modelling assumption, not discovered data.
- Planted artifacts are hand-authored fixtures and are labelled `synthetic`.
