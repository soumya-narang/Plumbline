# Demo script: three minutes, one story

The story: **an advisory appears, the affected service and its path are found, a later fact breaks an assumption behind a decision,
exactly that decision reopens, and the fix is handed off.** Everything else on the site is supporting evidence. Do not tour it.

Every step below was run against the current build, and the text quoted from the screen is what it showed.

## Before you start (once per take)

```bash
docker compose up -d
python -m plumbline load
python scripts/reset_demo.py          # empties the work queue, playbooks and saved approvals
python -m plumbline serve             # http://127.0.0.1:8000
```

Open <http://127.0.0.1:8000> in a **private window** so you are a fresh visitor (the site keeps approvals per visitor, by cookie).
Keep a terminal open in the project folder for the last step. For a retake, run `scripts/reset_demo.py`, restart the server, and use a new private window.

## The script

| Time | Do | Say |
|---|---|---|
| 0:00 | Stay on the hero. | "On 4 August a maintainer account was compromised and `keyv` and the `cacheable` packages were poisoned within 25 minutes. **The advisories and the repository lockfiles are real. The service names and exposure are my declared mapping, and the exposed examples are four planted fixtures, so I never accuse a real project.**" |
| 0:25 | Scroll to **Replay the incident**. It lands on 11:19:14, when `keyv` was published. | Read the sentence on the page: "keyv was just poisoned. 2 services lock it, 3 can't be judged without a lockfile, 13 are clear." Add: "Three are *can't be judged* because there is no lockfile to read. It refuses to guess." |
| 0:40 | `planted/storefront` is already selected. Point at the path and the **Fix** card. | "It reaches `keyv@6.0.0` through three packages, and the fix is to bump `@acme/payments-sdk`. That path is one shortest-path query in FalkorDB." |
| 0:55 | Open **How this was decided**, click **Re-derive from the graph**. | It shows *"Verified: verdict, evidence, queries and data all match."* Say: "The receipt is not a signature. It proves the result is consistent with the data, and it catches tampering." |
| 1:10 | Press **Next event** nine times, or drag the weight, to **11:42:00**. Open the **Decisions** tab. | "Five decisions were recorded. Each one stored the facts it assumed, for example *the lockfile has not changed* and *keyv@4.5.4 is not named by the advisory*." |
| 1:25 | In **Try a what-if**: advisory `keyv`, version `4.5.4`, click **Add version**. | "Suppose the advisory also named 4.5.4. This is hypothetical and only I see it." The notice reads **"1 decision reopened: mochajs/mocha."** |
| 1:45 | Click **Review**. | "mocha was approved as *Cleared* on an assumption that just stopped being true, so it is now *Exposed*, through `eslint`. **Only that decision reopened. The other four stayed decided.** One traversal found it." |
| 2:10 | Open **Ask the agent**. Type `Hand off the fixes for keyv`. | Point at the tool calls: "The agent reaches the graph only through MCP tools, and every call is shown." The answer says the gateway and the storefront were queued, and that **11 exposures would exist only if the hypothetical were real, so no task was created: the queue is shared and holds real work only.** |
| 2:30 | Open **Decisions**: the work queue lists two waiting tasks. | "A triage agent hands fixes to remediation agents through the graph." |
| 2:40 | In the terminal: `python -m plumbline handoff-demo --workers 5` | It prints each worker's count and **"every task worked exactly once"**. "Five agents raced for the queue. The claim is one atomic write, so none was worked twice." |
| 2:55 | Stop. | "Auditable, time-aware triage, with decisions that reopen when their assumptions break." |

**Optional extra, 30 seconds:** open **Check yours**, choose *"Exposed: real project, unmodified, your own bad version"*, click **Check**. "This is a real, untouched lockfile. I
entered `keyv@4.5.4` as my own bad version, and the graph finds the real path through `eslint`."

**Alternative to the what-if, no typing:** press **Next event** once more from 11:42 to reach **12:45**. A scripted, labelled-hypothetical advisory revision reopens
`planted/billing-worker`. Use the what-if as the main beat, because the audience can see you choose the version.

## Lines to have ready

- **Why a graph?** "SQL could implement each piece: recursive paths, a join table for assumptions, a queue table. My own benchmark says it is as accurate and faster on lookups. What the
  graph gives me is one model: the evidence path, the decision pointing at the facts it assumed, PageRank, the shared queue, and a separate graph per upload with `GRAPH.COPY`, all in one
  store and one query language. Taking FalkorDB out means rebuilding five mechanisms and keeping them consistent."
- **Is it an agent?** "The default is a deterministic planner calling the same MCP tools a model would. A model is optional, picks tools and phrases answers, and cannot change a verdict.
  If it fails or answers without using a tool, the planner takes over and the page says so. It is deterministic by design, because this is security triage."
- **Is it a scanner?** "No. It is incident-specific triage. It reads npm lockfiles and checks the incident's six advisories plus versions you list."

## Questions to expect

| Question | Answer |
|---|---|
| Is the whole flow live, or recorded? | The footer badge says **Live graph** or **Recorded snapshots**. The replay, evidence and graph view work in both. Approvals, what-ifs, the work queue, free-text questions, receipt re-derivation and the checker need the live server. |
| Where do the real data come from? | `data/fleet.json` pins each repository to its last commit at or before 11:12 UTC with the lockfile's hash; advisories are real OSV records. Everything is evaluated *as of* a timestamp, so an advisory is invisible before it was published. See `docs/incident.md`. |
| What does a receipt protect against? | Tampering with a stored result and drift between result and data. It does not prove who approved anything and cannot show that a lockfile matches what is deployed, which is why that is listed as an assumption. |
| How robust is the parser and the isolation? | Hostile and malformed inputs, size and edge caps, concurrent uploads and per-visitor isolation are covered by tests, and the container was exercised end to end. Unsupported formats (yarn, pnpm, v1) are refused with a reason. |
| What happens on restart? | Recorded approvals survive (they are kept in a file, `PLUMBLINE_STATE_DIR`). What-ifs are forgotten by design because they are hypothetical. On a host whose disk is erased, point the state directory at persistent storage. |
| Did the real repositories get hit? | No. None locked a malicious version; `nestjs/nest` sat one patch below one. The exposed examples are the planted fixtures, labelled as such. |

## If something goes wrong

- **The live server will not start:** open the GitHub Pages copy. It plays the same replay from recorded snapshots and says which features need a server.
- **A step shows nothing:** hard refresh (Ctrl+Shift+R) and make sure you are on a private window with a fresh cookie.
- **The queue already holds tasks from an earlier take:** run `python scripts/reset_demo.py`, restart the server.
