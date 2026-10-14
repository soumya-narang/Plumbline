# Plumbline

An agent that answers "are we exposed?" for a software supply-chain incident with a FalkorDB path or an explicit
refusal, and remembers every accepted risk together with the assumptions it rests on. When a new fact breaks an
assumption, exactly the affected decisions reopen.

Built for [Graph Hacks: Context for AI Agents](https://www.wemakedevs.org/hackathons/falkordb) (Oct 15-18, 2026).
Status: early scaffolding. Nothing here is a finished feature yet.

## Verdicts

| Verdict | Meaning |
|---|---|
| EXPOSED | An artifact locks an affected version, with the evidence path |
| CLEARED | Valid only relative to stated assumptions, stored as `ASSUMES` edges |
| UNKNOWN | Evidence is missing (for example no lockfile); the agent refuses to guess |

The LLM selects tools and phrases answers. Verdicts come from deterministic, unit-tested code in `policy`.

## Repository layout

```
docker-compose.yml     FalkorDB for local development (ports 6390 and 3010)
pyproject.toml         Python package and dev tooling
src/plumbline/         Application code (ingest, graph, policy, agent, api)
queries/               One named .cypher file per query the product depends on
tests/                 Unit tests; policy tests come first
data/raw/              Bulk downloads, git-ignored and re-fetchable
data/processed/        Versioned, hashed JSONL that the demo loads
docs/                  Verified engine behaviour, incident selection, data model
scripts/               Repeatable one-off tooling
```

## Quick start

```bash
cp .env.example .env
docker compose up -d
```

FalkorDB listens on `localhost:6390`; the browser UI is at <http://localhost:3010>.

## Documents

- [docs/falkordb-engine.md](docs/falkordb-engine.md): what was verified against the running engine
- [docs/incident.md](docs/incident.md): the real incident chosen for the replay
