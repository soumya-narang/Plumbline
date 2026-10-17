# Plumbline

**Plumbline answers one question about a software supply-chain incident: "which of our services does the poisoned package reach, and how?"**
It answers with the dependency path found in a FalkorDB graph, or with an explicit refusal when the evidence is missing. It remembers every
accepted risk together with the assumptions that decision rests on, so when a new fact breaks an assumption, exactly the affected decisions
reopen.

It replays a real incident minute by minute: on 4 August 2026 a compromised maintainer account published trojanized releases of `keyv`,
`cache-manager` and the `@cacheable/*` packages within 25 minutes. It also lets you run the same analysis on your own `package-lock.json`.

Built for [Graph Hacks: Context for AI Agents](https://www.wemakedevs.org/hackathons/falkordb) (15 to 18 October 2026).

---

## Contents

1. [What this project consists of](#what-this-project-consists-of)
2. [The incident and the data](#the-incident-and-the-data)
3. [How a verdict is produced](#how-a-verdict-is-produced)
4. [The website, section by section](#the-website-section-by-section)
5. [The lockfile checker](#the-lockfile-checker)
6. [The agent and its tools](#the-agent-and-its-tools)
7. [Memory and coordination](#memory-and-coordination)
8. [Graph data model and queries](#graph-data-model-and-queries)
9. [HTTP API](#http-api)
10. [Measured results](#measured-results)
11. [Safety, limits and hardening](#safety-limits-and-hardening)
12. [Tests and verification](#tests-and-verification)
13. [Run it](#run-it)
14. [Repository layout](#repository-layout)
15. [What is real, declared, scripted, and not done](#what-is-real-declared-scripted-and-not-done)
16. [Hackathon tracks](#hackathon-tracks)
17. [Further documents](#further-documents)

---

## What this project consists of

| Part | What it is | Where |
|---|---|---|
| **Graph** | FalkorDB holds 18 repositories, 12,370 locked packages, 22,675 dependency edges, 6 advisories, plus decisions, facts, receipts, tasks and playbooks | `src/plumbline/graph`, `queries/` |
| **Verdict policy** | Deterministic code that turns graph evidence into EXPOSED, CLEARED or UNKNOWN. No model is involved | `src/plumbline/policy` |
| **Receipts** | A hash-checked record of how each verdict was derived, which can be re-derived from the graph | `src/plumbline/triage/receipt.py` |
| **Decision memory and replay** | Approvals recorded with the facts they assume; a replay engine that moves the incident backwards and forwards in time | `src/plumbline/memory` |
| **Agent** | An MCP server with 12 tools, a built-in planner, and an optional language-model backend that fails safe | `src/plumbline/agent` |
| **Work queue** | A shared queue in the graph through which a triage agent hands fixes to remediation agents, with playbook memory | `src/plumbline/memory/tasks.py` |
| **Website** | A dependency-free front end (vanilla JavaScript modules): the replay, the checker, and an explanation of how it works | `web/` |
| **Lockfile checker** | Upload an npm lockfile, get its own isolated graph and a verdict with the path and the queries that ran | `src/plumbline/tenants.py`, `web/check.html` |
| **HTTP API** | FastAPI app serving the site and JSON | `src/plumbline/api` |
| **Benchmark** | The graph, SQLite and text retrieval graded against `npm ls` | `src/plumbline/bench`, `docs/benchmark.md` |
| **Deployment** | One Docker image (FalkorDB plus app), a GitHub Pages workflow for the static site, a Hugging Face Space definition | `Dockerfile`, `deploy/`, `.github/workflows/pages.yml` |

The site runs in two modes:

- **Live** (a server is running): everything below works.
- **Recorded** (the GitHub Pages copy, no server): the replay, evidence, graph view, decisions and the seven suggested agent questions
  are served from pre-computed snapshots of the same data. Free-text questions, approvals, what-ifs, the work queue, the receipt
  re-derivation and the lockfile checker need a server, and the site says so where they would appear.

---

## The incident and the data

On 2026-08-04 the following malicious releases appeared on npm (OSV records, all published within 25 minutes, UTC):

| OSV id | Package | Malicious version | Published |
|---|---|---|---|
| `MAL-2026-11523` | `cache-manager` | 7.2.10 | 11:12 |
| `MAL-2026-11524` | `keyv` | 6.0.0 | 11:19 |
| `MAL-2026-11560` | `@cacheable/node-cache` | 3.1.2 | 11:34 |
| `MAL-2026-11558` | `@cacheable/memory` | 2.2.1 | 11:35 |
| `MAL-2026-11561` | `@cacheable/utils` | 2.5.1 | 11:36 |
| `MAL-2026-11559` | `@cacheable/net` | 2.1.1 | 11:37 |

Sources and the selection of this incident are in [docs/incident.md](docs/incident.md).

### The fleet: 18 repositories

| Kind | Count | Notes |
|---|---|---|
| Real public repositories with a parsed lockfile | 11 | `nestjs/nest`, `axios/axios`, `serverless/serverless`, `mochajs/mocha`, `nodemailer/nodemailer`, `lerna/lerna`, `apollographql/apollo-server`, `socketio/socket.io`, `npm/cli`, `winstonjs/winston`, `microsoft/TypeScript`; each pinned to its last commit at or before 11:12 UTC on the day |
| Real repositories whose verdict can only be UNKNOWN | 3 | `eslint/eslint` and `sindresorhus/got` commit no lockfile; `typeorm/typeorm` uses a lockfile format the parser does not read |
| Planted fixtures (labelled synthetic everywhere) | 4 | `orders-api`, `gateway`, `billing-worker`, `storefront`; hand-authored lockfiles so the demo can show EXPOSED without accusing a real project. See [data/fixtures/planted/README.md](data/fixtures/planted/README.md) |

Finding on the real repositories: **none locked a malicious version.** `nestjs/nest` sat one patch below one (`cache-manager@7.2.9`
against malicious `7.2.10`).

A **declared deployment overlay** (`data/overlay.json`) assigns each repository a service name, an exposure (internet-facing or internal) and a tier.
It is a modelling assumption, not discovered data, and the site labels it that way.

All graph data is loaded from committed, versioned, hashed JSONL in `data/processed/`, so the demo never depends on a live API. The pipeline
that produced it (`pin-fleet`, `build-data`) is included and re-runnable.

---

## How a verdict is produced

The graph supplies **evidence**: what each repository locks, what an advisory names, and the dependency path between them. Plain, unit-tested
code in `src/plumbline/policy` then **decides**. A language model can choose tools and phrase an answer; it can never produce or change a verdict.

| Verdict | Meaning |
|---|---|
| **EXPOSED** | The repository locks a version the advisory names. Carries the evidence, the shortest dependency path, the direct dependency to bump, and a receipt |
| **CLEARED** | True only relative to stated assumptions, stored as `ASSUMES` edges: that the lockfile matches what is deployed, and that the advisory's list of affected versions is complete |
| **UNKNOWN** | Evidence is missing (no lockfile, or an unsupported format). Plumbline refuses to guess, and says what would settle it |

**Receipts.** Each verdict has a receipt: a payload (verdict, evidence, path, assumptions, policy version) and its hash. Verification
checks the hash first, then re-derives the verdict from the live graph, so both an edited receipt and a forged one with a recomputed hash are
rejected. Tested.

**What a receipt protects against, and what it does not.** A receipt shows that a verdict is *consistent*: the stated evidence hashes to the stated value, and the graph, asked again,
reaches the same verdict. It catches tampering with a stored result and any drift between the result and the data. It is **not a digital signature**: it does not prove who produced
it or who approved a decision, and it cannot show that a lockfile matches what is actually deployed. That last point is exactly why every CLEARED and EXPOSED verdict lists
"the lockfile matches what is deployed" as an assumption.

**As-of semantics.** Everything is evaluated as of a timestamp. An advisory is invisible before its publication time, and a version added by a
later revision is invisible before that revision. This is what lets the replay move backwards as well as forwards.

---

## The website, section by section

### Home page (`/`)

**Navigation.** A floating pill bar: Replay, How it works, Under the hood, and (live mode only) Check yours; plus a light/dark theme toggle that follows
the system setting and remembers the choice. On wide screens a vertical "depth ruler" at the left edge (0 question, 1 replay, 2 method, 3 graph)
tracks which section you are reading; it fades out before the footer.

**Hero.** The question the product answers, with a plumb-line drawing of the poisoned path (service, direct dependency, two transitive packages, a bob at
`keyv@6.0.0`). Buttons lead to the replay and to the explanation.

**Replay the incident.** The working core of the site. One narration sentence reads the moment on screen, for example *"keyv was just poisoned. 2 services lock
it, 3 can't be judged without a lockfile, 13 are clear."* Below it are three panels:

1. **Timeline (left).** A UTC clock and the name of the current event; previous, play and next buttons; and a rail of **13 events** (before the first release, the six
   advisory publications, five recorded approvals, one labelled hypothetical advisory revision). You drag the weight along the rail, press play, or use the arrow
   keys. The position can be set from the URL (`?start=N`).
2. **Who is affected (middle).** An advisory selector, a stacked bar of exposed / can't be judged / cleared, and the repositories grouped by verdict. Each row shows the
   service, a "public" chip for internet-facing ones, and a "reopened" tag where a decision has reopened. Cleared repositories are collapsed by default.
3. **Detail (right), with four tabs:**
   - **Evidence.** The verdict, a plain sentence (for example *"It reaches keyv@6.0.0, a malicious release, through 3 packages"*), the dependency path drawn as a
     plumb line, and a **Fix** card naming the direct dependency to bump. If a decision has reopened it explains which assumption broke and when. A **Decision** block
     lets a visitor record an approval (live mode). A closed "How this was decided" section holds the assumptions, the receipt hash, a **Re-derive from the graph**
     button, and the Cypher query that found the path.
   - **Graph.** The repository's whole dependency tree drawn on a canvas, with hover-to-trace and the poisoned path lit.
   - **Decisions.** Every recorded decision with who approved it and when, a *Reopened* badge where relevant; below it a **"Try a what-if"** form (live mode) and the
     shared **work queue** (live mode). See [Memory and coordination](#memory-and-coordination).
   - **Ask the agent.** Seven suggested questions, a free-text box (live mode), and a trace showing every tool call the agent made with its duration, followed by the
     answer and a line stating who wrote it (the built-in planner or a named model, or the planner stepping in with the reason).

When a decision reopens, a notice appears above the tabs with a **Review** button that jumps to the affected repository.

**How it works.** Three short explanations (*Show the path, not a score*; *Say what you assumed*; *Reopen only what broke*), then a **"Then try it on your own project"** block
with the three steps for the checker and a button to it (live mode; the recorded copy explains that it needs a server).

**Under the hood.** "One graph does three jobs" (evidence, memory, tools), live figures from the loaded graph, a **Cypher viewer** with tabs for the four key queries
(evidence path, reopen, fix first, PageRank), and **"Measured, not claimed"**: the benchmark as bars and a table.

**Footer and status.** Badges say whether the site is on the live graph or recorded snapshots and which agent backend is active, with a link to the source.

### Lockfile checker (`/check.html`)

Described in [the next section](#the-lockfile-checker). It is a separate page with its own styling.

### Behaviour across devices and themes

Light and dark themes; layouts for desktop, tablet and phone widths; no horizontal page scrolling; reduced-motion support. Fonts are bundled
(no external requests).

---

## The lockfile checker

Open `/check.html` (live mode). Paste or choose a `package-lock.json`, optionally name it, optionally list your own bad versions, and click **Check**.

**What happens.** Your lockfile becomes its own graph: each locked package a node, each requirement an edge. The graph is created from a template graph with FalkorDB's
`GRAPH.COPY`, so uploads cannot see each other or the main fleet graph. The same queries and the same policy as the replay judge it.

**What you see.**
- A headline (**Exposed**, **Clear**, or **Could not be decided**) and, when exposed, which direct dependency to bump.
- Counts: installs, requirement edges, packages checked.
- One card per finding with the verdict, the path (`eslint → file-entry-cache → flat-cache → keyv`), who pulled it in, and the stated assumptions. Cleared findings are collapsed.
- **"How the graph found it":** a drawing of only the installs on the poisoned paths, and the three Cypher queries that ran, with a one-line description of each.
- A **Delete this check now** button.

**What you can upload.** An npm `package-lock.json` or `npm-shrinkwrap.json`, `lockfileVersion` 2 or 3, plain JSON, up to 4 MB, 8,000 packages and 20,000 dependency links.
`yarn.lock`, `pnpm-lock.yaml` and v1 lockfiles are refused with a reason. Nothing is installed or executed; only the lockfile's structure is read.

**Your own bad versions.** An expandable box accepts up to ten `package@version` lines (scoped names work). They are loaded into your graph as an advisory and judged
exactly like the incident. So it is not tied to one incident, although it only checks the versions named by the incident and by you; it is not a general vulnerability scanner.

**Samples** (a dropdown, generated by `scripts/make_check_samples.py`):

| Sample | Result |
|---|---|
| Hand-authored lockfile, poison three levels deep | Exposed (3 findings) |
| Real nodemailer lockfile with one version edited to the poisoned release | Exposed through the real path `eslint → file-entry-cache → flat-cache → keyv@6.0.0` |
| Real nodemailer lockfile, unmodified | Clear: it contains `keyv@4.5.4`, so a text search would flag it, but that version is not named |
| Same unmodified real lockfile plus your own bad version `keyv@4.5.4` | Exposed through the same real path, with no change to the file |

The 16 real lockfiles from the project's data directory were also run through it and all behave correctly. To cross-check a verdict against `npm` itself, put the lockfile and a matching
`package.json` in a folder and run `npm ls keyv --package-lock-only --offline`.

**Limits.** Three open checks per client, 25 in total, each deleted after 30 minutes, and a clear message saying how long to wait when full.

---

## The agent and its tools

The agent reaches the graph only through an **MCP server** (`python -m plumbline.agent.mcp_server`, also used in memory by the app). It exposes 12 tools:

| Tool | Writes? | What it does |
|---|---|---|
| `list_advisories` | no | Advisories published by a given time |
| `triage_advisory` | no | Every repository against one advisory: counts and the rows needing attention, with paths and receipts |
| `explain_path` | no | One repository's verdict: evidence, path, assumptions |
| `reopen_check` | no | Decisions whose assumptions have been contradicted |
| `propose_decision` | no | Describes the decision that would be recorded; writes nothing |
| `fix_first` | no | Ranks the direct dependencies to bump by how many repositories they expose (fleet-wide query) |
| `critical_dependencies` | no | PageRank over one repository's dependency graph |
| `list_decisions` | no | Recorded decisions and their status |
| `hand_off_fix` | queue only | Adds a fix for one EXPOSED repository to the shared work queue; the fix is taken from the graph, not the caller |
| `claim_task` | queue only | Takes the oldest open task, atomically |
| `complete_task` | queue only | Finishes a task you claimed and records how it was resolved |
| `list_tasks` | no | The work queue |

**Approving a decision is deliberately not a tool.** Only a person can approve, through the site.

**Two interchangeable backends share one trace format:**
- **Built-in planner** (default): rule-based, deterministic, no model and no key. It recognises questions about exposure, paths, reopened decisions, fix-first, critical
  dependencies, decisions, hand-offs and the queue.
- **Language model** (optional): set `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` for any server that speaks the chat-completions tool-calling protocol. It chooses tools and
  phrases the answer. It fails safe: on a timeout (`LLM_TIMEOUT`), an error, malformed tool arguments, or an answer given without calling any tool, the agent answers with the
  planner and states why on the page. Model calls are capped per hour.

Either way, the verdicts on the page come from the tool results, never from the answer's prose.

---

## Memory and coordination

| Kind of memory | What it is | Where |
|---|---|---|
| **Episodic** | Decisions: who approved what, when, and with which verdict | `memory/decisions.py` |
| **Semantic** | Facts a decision assumed (`lock_snapshot`, `not_affected`) and the query that finds decisions a changed fact breaks | `queries/q5_reopen_check.cypher` |
| **Procedural** | Playbooks: how a package was fixed last time, offered on the next hand-off for that package | `memory/tasks.py` |

**Reopening.** An accepted decision stores `ASSUMES` edges to the facts it rests on. When a later event contradicts a fact, one query finds exactly the decisions that assumed it,
and only those reopen and are re-evaluated. Everything else stays decided.

**The recorded replay** applies five recorded approvals and one scripted, clearly labelled hypothetical event (a second poisoned `keyv` release added to the advisory), which reopens
exactly one decision (`billing-worker`, cleared on the assumption that `keyv@6.0.1` was not named).

**Try a what-if.** Because the real advisory only ever named `keyv@6.0.0`, no real revision exists to replay. So a visitor can add any version to any advisory from the time on the clock and watch which
decisions reopen (for example adding `keyv@4.5.4` reopens the approved-as-cleared `mocha` decision, flipping it to EXPOSED). What-ifs are hypothetical, belong to that visitor, and never
touch the recorded incident. They can be removed with one click.

**Per-visitor state.** The graph holds one set of decision memory, and every request first rewinds it to that visitor's own history (approvals and what-ifs, kept by a session cookie)
before reading or writing. One visitor never sees another's approvals.

**Durability.** Approvals are decisions, so they are appended to a file (`data/state/approvals.jsonl`, or `$PLUMBLINE_STATE_DIR`) and reloaded when the server starts: a restart does not
lose them, and the visitor's cookie gets them back. A damaged file is read line by line, anything malformed is ignored, and the file is compacted on load. What-ifs are hypothetical and are
deliberately kept in memory only. "Remove my what-ifs" removes only what-ifs, never approvals. On a host with an ephemeral disk, point `PLUMBLINE_STATE_DIR` at persistent storage.

**The work queue.** A triage agent finds every EXPOSED repository and hands each fix to a queue stored in the graph (`Task` nodes). Remediation agents claim the oldest open task,
work it, and complete it. Claiming is a single Cypher write, and FalkorDB runs write queries on one graph one at a time, so two agents cannot receive the same task. A test races
20 threads for 40 tasks and checks each is claimed exactly once. Completing a task records a `Playbook` for that package, and the next hand-off returns it as a suggestion.
The queue is shared, so it holds real work only: an exposure that exists only because of a hypothetical revision (the scripted one, or a visitor's what-if) is refused, and the agent says how many it declined. If a repository is exposed both by a real version and by a what-if one, the task's path and fix come from the real version alone. The queue is visible under the Decisions tab and via `GET /api/tasks`.

```bash
python -m plumbline handoff-demo --workers 5     # 7 real exposures (1 resting on the hypothetical revision is skipped), 5 concurrent agents, every task worked exactly once
```

**Tenants.** The lockfile checker gives each upload its own graph (see above), and approvals and what-ifs are kept per visitor.

---

## Graph data model and queries

```
(Service)-[:RUNS]->(Artifact)-[:LOCKS]->(LockedDep)-[:REQUIRES]->(LockedDep)
(Service)-[:EXPOSED_VIA]->(Exposure)            (LockedDep)-[:IS]->(PackageVersion)<-[:AFFECTS]-(Advisory)
(Decision)-[:ABOUT]->(Advisory)   (Decision)-[:FOR]->(Artifact)   (Decision)-[:ASSUMES]->(Fact)   (Receipt)-[:PROVES]->(Decision)
(Task)-[:ABOUT]->(Advisory)       (Task)-[:FOR]->(Artifact)       (Task)-[:USED]->(Playbook)
```

Dependencies are modelled per repository (`LockedDep`), so "which service reaches the poisoned version, and through what" is one variable-length path query, not a join per hop. Nodes:
`Artifact`, `LockedDep`, `PackageVersion`, `Advisory`, `Service`, `Exposure`, `Decision`, `Fact`, `Receipt`, `Task`, `Playbook`. Range indexes and unique constraints are listed in
[docs/data-model.md](docs/data-model.md), which also records the known limits.

The Cypher the product depends on, all in `queries/`:

| Query | What it answers |
|---|---|
| `q1_exposure_base` | Which services lock a version an advisory names |
| `q2_explain_path` | The shortest dependency path from a service to the poisoned version (`shortestPath` over `REQUIRES*0..8`) |
| `q5_reopen_check` | Which accepted decisions assumed a fact that is no longer true |
| `q6_fix_first` | Which direct dependency to bump to clear the most exposure, across the fleet |
| `q7_critical_dependencies` | PageRank (`algo.pageRank`) over one repository's dependency graph |
| `triage/*` | Evidence gathering used by every verdict |
| `memory/*` | Committing, listing, reopening and resetting decisions during replay |
| `work/*` | Creating, atomically claiming, completing and listing tasks; recording and finding playbooks |
| `tenant/*` | Stamping, sizing and describing per-upload graphs |
| `load/*`, `graph/*`, `bench/*` | Loading the graph, exporting it for the graph view, the benchmark's FalkorDB side |

---

## HTTP API

| Route | Purpose |
|---|---|
| `GET /api/health`, `GET /api/meta` | Status, timeline, graph statistics, the key queries, agent backend |
| `GET /api/snapshot?at=` | Everything the replay needs for one moment, for the calling visitor |
| `GET /api/graph?artifact=` | One repository's dependency graph for the graph view |
| `POST /api/ask` | Ask the agent (planner or model); returns the tool-call trace and the answer |
| `POST /api/approve` | Record a person's approval (per visitor, rate limited, can be switched off) |
| `POST /api/revise`, `DELETE /api/revise` | Add or clear a visitor's what-if advisory revision |
| `GET /api/tasks?status=` | Read the work queue (read-only over HTTP; agents write it through MCP) |
| `GET /api/receipt`, `POST /api/verify` | Produce a receipt; re-derive and verify one |
| `POST /api/check`, `GET /api/check/{id}`, `GET /api/check/{id}/graph`, `DELETE /api/check/{id}` | The lockfile checker |
| `GET /api/openapi.json` | The OpenAPI description |

Command line (`python -m plumbline <command>`): `load`, `serve`, `query`, `triage`, `replay`, `verify`, `handoff-demo`, `export-static`, `benchmark`, `pin-fleet`, `build-data`.

---

## Measured results

The same lockfile questions are answered by the graph, by SQLite and by text retrieval, and graded against `npm ls --package-lock-only --offline`, which shares nothing with this project's
parser or graph (`python -m plumbline benchmark`, full output in [docs/benchmark.md](docs/benchmark.md)). Ten repositories could be graded; eight were excluded and each exclusion is listed
(workspaces, unsupported or absent lockfiles).

| Question | Graph (FalkorDB) | SQL, tuned | Text retrieval |
|---|---|---|---|
| Does A lock P@V? (70 questions) | 100% | 100% | 100% |
| Which direct dependencies pull P@V in? (16, multi-hop) | 100% | 100% | 44% |
| Which artifacts lock P@V? (7, fleet-wide) | 100% | 100% | 86% |

**Stated plainly:** a tuned in-process SQL query gets the same answers and is faster on lookups at this size. Text retrieval fails the multi-hop question. The graph's case is not speed.

**What this table does and does not show.** It grades dependency *lookups* only. It does not claim the graph is better for the whole workflow, and SQL could implement each piece
of that workflow on its own: a recursive query for paths, a join table for assumptions, a queue table for hand-offs. The case for the graph is the integrated model. The evidence (a path),
the memory (a decision pointing at the facts it assumed, so one traversal finds what a new fact breaks), the algorithms (`PageRank` is built in and runs on the same data), the shared
state (agents hand work to each other through the same store they query) and the isolation (`GRAPH.COPY` gives every upload its own graph in one instance) all live in one place and are
queried in one language. Taking FalkorDB out would mean rebuilding each of those as a separate mechanism and keeping them consistent with each other.

The benchmark also caught a real bug in this project's own parser: peer dependencies were being treated as installs, which could name the wrong package to bump. It is fixed and tested.

---

## Safety, limits and hardening

| Area | What is in place |
|---|---|
| Lockfile uploads | Parsed, never installed or run. Size, package and edge caps. Deeply nested or malformed JSON returns a clean 422. Cypher is fully parameterised (an injection attempt in a package name does nothing) |
| Isolation | One FalkorDB graph per upload; 32-character random ids; per-visitor approval history; separate session cookie (`HttpOnly`, `SameSite=Lax`) |
| Fair use | 3 open checks per client, 25 total, 30-minute lifetime; 10 approvals or what-ifs per hour per address and 20 per session; model calls capped per hour; the work queue holds at most 50 unfinished tasks |
| Concurrency | The checker never holds a global lock while loading a graph; claiming a task is one atomic write; FalkorDB is started with 500 queued queries and a 5 s read timeout (its defaults are 25 and 1 s) |
| HTTP | Content-Security-Policy that allows scripts only from the site itself, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, a restrictive Permissions-Policy, framing allowed only by the site and Hugging Face; no inline scripts; pages revalidated on every load |
| Output | All dynamic text is escaped before display; the checker builds its page with `textContent` |
| Read-only mode | `PLUMBLINE_APPROVALS=off` disables recording approvals; `PLUMBLINE_TRUST_PROXY=1` counts visitors by `X-Forwarded-For` behind a proxy (set in the image) |
| Durability | Approvals are appended to a file and reloaded at start; a damaged file is read line by line and compacted; what-ifs stay in memory only |
| Honest failure | A failing model never breaks the agent or shows ungrounded text; a refused upload leaves no graph behind |

One thing found during hardening is worth recording: FalkorDB can panic on a query that returns a property no node in that graph has ever had. Every uploaded graph is therefore stamped with
all its properties before it becomes visible to any other request, and a regression test covers it.

---

## Tests and verification

**209 automated tests** (`pytest`), covering:

| Area | Examples |
|---|---|
| Parser and policy | Lockfile v2/v3 resolution, peer-dependency rule, verdict logic, assumptions |
| Graph and triage | Loading, paths, as-of semantics, receipts (tampering and forged-hash cases) |
| Memory and replay | Decisions, reopening, replay backwards and forwards, approvals surviving a scrub |
| Agent | Tool listing, planner answers, two agents over MCP, model failure fallbacks and the grounding guard |
| Work queue | Atomic claiming (20 threads, 40 tasks), idempotent hand-off, claimer-only completion, playbook recall, bounded queue, replay never touching the queue |
| Checker | Isolation between uploads, hostile and malformed input, limits, expiry, concurrent uploads, failed loads, the samples' stated verdicts, custom bad-version lists |
| Visitors and API | Per-visitor approvals and what-ifs, rate limits, cookie handling, security headers, path traversal, HEAD, read-only mode |
| Benchmark and export | Oracle grading, static export consistency |

Integration tests need FalkorDB running and skip themselves otherwise. The Docker image was built and exercised end to end (health, headers, the checker with real and edited lockfiles,
per-client limits, per-visitor isolation, a what-if reopen, an agent hand-off and the queue).

---

## Run it

**Locally**

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"      # on macOS/Linux: .venv/bin/python
cp .env.example .env
docker compose up -d                                  # FalkorDB on localhost:6390, browser on :3010
python -m plumbline load                              # rebuild the graph from data/processed
python -m plumbline serve                             # http://127.0.0.1:8000
pytest
```

Try the terminal commands:

```bash
python -m plumbline triage MAL-2026-11524 --at 2026-08-04T11:40:00Z --receipts data/raw/receipts   # who is exposed, with paths
python -m plumbline verify data/raw/receipts/MAL-2026-11524__planted__gateway.json                 # re-derive a receipt
python -m plumbline replay --to 2026-08-04T13:00:00Z                                               # exactly one decision reopens
python -m plumbline handoff-demo --workers 5                                                       # agents passing work
python -m plumbline benchmark                                                                      # graph vs SQL vs retrieval
```

**One container.** `docker build -t plumbline .` produces an unprivileged image with FalkorDB and the app (port 7860). **Static site.** `python -m plumbline export-static`
writes recorded snapshots into `web/data`; the GitHub Pages workflow publishes `web/`. **Hugging Face Space:** see [docs/deploy.md](docs/deploy.md), which also lists the settings for a
public deployment (`PLUMBLINE_APPROVALS`, `PLUMBLINE_TRUST_PROXY`, `LLM_*`).

To regenerate the data from scratch (needs `git` and network access): `python -m plumbline pin-fleet`, then `python -m plumbline build-data`.

---

## Repository layout

```
docker-compose.yml     FalkorDB for local development (ports 6390 and 3010)
Dockerfile             FalkorDB, API and UI in one unprivileged container
pyproject.toml         Python package and dev tooling
src/plumbline/
  ingest/              npm lockfile parser, fleet pinning, OSV advisories, processed JSONL builder
  graph/               connection, schema, loader
  policy/              deterministic verdicts (pure functions, no database)
  triage/              graph-backed evidence gathering, receipts
  memory/              decisions, assumptions, replay, work queue and playbooks, hand-off demo
  agent/               typed tools, MCP server, built-in planner, optional model backend
  api/                 FastAPI app, per-visitor sessions and limits
  tenants.py           one graph per uploaded lockfile
  snapshot.py          everything the UI needs for one moment; export_static.py writes them all
  bench/               the graph vs SQL vs retrieval benchmark and its npm oracle
  cli.py               `python -m plumbline <command>`
queries/               One named .cypher file per query, grouped by purpose
web/                   Dependency-free UI (vanilla JS modules); web/data is the static export; web/samples are the checker's samples
deploy/                Container entrypoint and the Hugging Face Space settings
.github/workflows/     GitHub Pages deployment
tests/                 Unit and integration tests
data/                  incident.json, fleet.json, replay.json, overlay.json, fixtures/planted, processed (committed), raw (git-ignored)
docs/                  Engine behaviour, incident, data model, deployment, benchmark
scripts/               probe_fleet.py, make_storefront_fixture.py, make_check_samples.py
```

---

## What is real, declared, scripted, and not done

**Real**
- The incident, its six OSV advisories and their publication times.
- 14 public repositories pinned to their commit before the first malicious release, and their real lockfiles (11 parsed; 3 cannot be judged).
- The dependency edges, the verdicts, the paths, the PageRank scores, the benchmark and its npm oracle.

**Declared (a modelling assumption, labelled in the UI)**
- Which service runs each repository, how exposed it is, and its tier (`data/overlay.json`).
- The four planted fixtures, which are hand-authored (one is generated from a real lockfile with one fictional dependency added).

**Scripted (labelled hypothetical wherever shown)**
- The single advisory revision at 12:45 in the recorded replay. The real advisory only ever named `keyv@6.0.0`; no real revision exists. Visitors can author their own what-ifs.
- The five recorded approvals are recorded actions, not live ones.

**Limits worth knowing**
- The default agent is a rule-based planner, not a language model. A model can be plugged in and fails safe, but this repository contains no recorded model traces.
- Only npm lockfiles v2 and v3 are read; yarn, pnpm and v1 are refused.
- The checker only knows the incident's six advisories and whatever versions the user lists; it is not a general vulnerability database.
- A tuned SQL query answers the lookup questions as correctly, and faster, as the graph does. The benchmark states this.
- Approvals survive a restart (they are kept in a file); what-ifs are forgotten on restart by design; the work queue lives in the graph and is cleared when the graph is rebuilt. On a host whose disk is erased on restart, set `PLUMBLINE_STATE_DIR` to persistent storage or approvals go with it.
- The benchmark graded 10 of 18 repositories (the other 8 are excluded for stated reasons).
- Integration tests require a running FalkorDB.
- The recorded GitHub Pages copy has no checker, no free-text agent, no approvals and no work queue; it says so where those would be.

---

## Hackathon tracks

**Track 01, Agents That Act on Connected Data** is the core. An agent triages a supply-chain incident by following dependency paths (a shortest-path query), ranks what to fix first
(a fleet query), and finds the packages a project leans on most (PageRank), all through MCP tools, with every verdict explained by its path and a receipt that can be re-derived.

**Track 02, Agent Memory and Coordination** is covered by working, tested parts:

| Track 02 focus | Where it is |
|---|---|
| Episodic memory | Decisions, with who approved and when |
| Semantic memory | Facts a decision assumed, and the reopen query |
| Procedural memory | Playbooks recalled on the next hand-off |
| Shared state and hand-offs | The work queue in the graph (`handoff-demo`) |
| Concurrent reads and writes | 20 agents racing for 40 tasks, each claimed exactly once; concurrent uploads stay separate |
| Separate memory per user or tenant | One graph per uploaded project via `GRAPH.COPY`; approvals and what-ifs per visitor |

---

## Further documents

- [docs/falkordb-engine.md](docs/falkordb-engine.md): behaviour verified against the running engine
- [docs/incident.md](docs/incident.md): the real incident chosen for the replay
- [docs/data-model.md](docs/data-model.md): nodes, edges, indexes and known limits
- [docs/benchmark.md](docs/benchmark.md): the full ablation with its first wrong answers
- [docs/deploy.md](docs/deploy.md): GitHub Pages and Hugging Face Space deployment and public-deployment settings
- [docs/demo-script.md](docs/demo-script.md): a three-minute walkthrough of the one end-to-end story, with the answers to likely questions
- [data/fixtures/planted/README.md](data/fixtures/planted/README.md): what each planted fixture is for
