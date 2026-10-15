# Ablation: graph, SQL and naive retrieval

Generated 2026-10-15T11:47:18Z on Windows-11-10.0.26200-SP0 with Python 3.13.14. Gold answers come from `npm ls --package-lock-only --offline` (npm 11.19.0), which does not use this project's parser, graph or policy.

10 artifacts were graded; 8 were excluded: serverless/serverless (uses workspaces), lerna/lerna (uses workspaces), apollographql/apollo-server (uses workspaces), socketio/socket.io (uses workspaces), npm/cli (uses workspaces), typeorm/typeorm (lockfile unsupported), eslint/eslint (lockfile absent), sindresorhus/got (lockfile absent).

| Question | Questions | Graph (FalkorDB) | SQL, tuned (SQLite) | SQL, first attempt | Retrieval (BM25) |
|---|---|---|---|---|---|
| Does A lock P@V? (single hop) | 70 | 70/70 (100%), p50 1.27 ms | 70/70 (100%), p50 0.002 ms | 70/70 (100%), p50 0.002 ms | 70/70 (100%), p50 18.168 ms |
| Which direct dependencies pull P@V in? (multi hop) | 16 | 16/16 (100%), p50 1.664 ms | 16/16 (100%), p50 0.618 ms | 16/16 (100%), p50 113.187 ms | 7/16 (44%), p50 78.628 ms |
| Which artifacts lock P@V? (fleet wide) | 7 | 7/7 (100%), p50 2.742 ms | 7/7 (100%), p50 0.005 ms | 7/7 (100%), p50 0.005 ms | 6/7 (86%), p50 17.703 ms |

Non-comment lines of query for the multi-hop question: Cypher 6, tuned SQL 8, first-attempt SQL 10 (both recursive).

Latency is the median of three runs per question, on one machine, with FalkorDB reached over a local socket; treat it as indicative, not a benchmark claim.

First wrong answers from retrieval:

```json
[
 {
  "kind": "pulled_by",
  "artifact": "nestjs/nest",
  "target": "keyv@4.5.4",
  "expected": [
   "eslint"
  ],
  "answered": [
   "cache-manager"
  ]
 },
 {
  "kind": "pulled_by",
  "artifact": "axios/axios",
  "target": "keyv@4.5.4",
  "expected": [
   "eslint"
  ],
  "answered": []
 },
 {
  "kind": "pulled_by",
  "artifact": "mochajs/mocha",
  "target": "keyv@4.5.4",
  "expected": [
   "eslint"
  ],
  "answered": []
 }
]
```
