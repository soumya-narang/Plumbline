# Incident for the replay: keyv / cacheable compromise, 2026-08-04

Selected at gate G0 from real OSV records. All facts below were read from `api.osv.dev` on 2026-10-15.

## What happened

OSV record `MAL-2026-11524` states that `keyv@6.0.0` is a trojanized release published on 2026-08-04, pushed through a
compromised maintainer account behind the `keyv` and `cacheable` package families. The malicious releases reached npm with
a valid provenance attestation. Delivery is through the npm install lifecycle.

Primary references listed in the record:
[Socket](https://socket.dev/blog/popular-npm-packages-in-the-keyv-and-cacheable-namespaces-compromised-in-active-supply-chain),
[Aikido](https://www.aikido.dev/blog/keyv-and-friends-compromised-in-npm-supply-chain-attack),
[SafeDep](https://safedep.io/keyv-npm-supply-chain-compromise/),
[GHSA-3p9h-f68w-m6fx](https://github.com/advisories/GHSA-3p9h-f68w-m6fx).

## The core burst (the replay's first act)

All published on 2026-08-04, within 25 minutes (UTC):

| OSV id | Package | Malicious version | Published |
|---|---|---|---|
| MAL-2026-11523 | `cache-manager` | 7.2.10 | 11:12 |
| MAL-2026-11524 | `keyv` | 6.0.0 | 11:19 |
| MAL-2026-11560 | `@cacheable/node-cache` | 3.1.2 | 11:34 |
| MAL-2026-11558 | `@cacheable/memory` | 2.2.1 | 11:35 |
| MAL-2026-11561 | `@cacheable/utils` | 2.5.1 | 11:36 |
| MAL-2026-11559 | `@cacheable/net` | 2.1.1 | 11:37 |

## The wider wave (the replay's second act)

Further `MAL-` records published the same day (13:17 to 18:00 UTC) for unrelated scopes, for example `@nebula.js/*`,
`@hubsync/web-sdk-react`, `@arv-bedrock/*`, `@deliveroo/*` and `@adminide-stack/*`. Whether these belong to the same
campaign was **not verified**: the filter that found them matched loosely. Treat them as same-day malicious releases
until a source ties them together, and label them that way in the UI.

## Why this incident

- Real, dated and recent, with a tight publish burst that makes a timeline slider meaningful.
- `keyv` and `cache-manager` are expected to be common transitive dependencies (to be confirmed against the repo fleet), which would give exposure paths of depth 3 or more.
- The "valid provenance, compromised source" detail supports the project's point: a trust signal is not proof of safety.

## Open checks (before the data is committed)

- Licence terms of the OSV `MAL-` records and of the upstream `ossf/malicious-packages` repository.
- Whether the record's version lists are complete (some packages list several malicious versions).
- Only metadata and derived edges are stored. Malicious package contents are never downloaded or redistributed.
