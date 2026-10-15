# Planted fixtures

Three hand-authored lockfiles, labelled synthetic everywhere they appear. They exist so the demo can show an
EXPOSED verdict without making any claim about a real third-party repository.

| Fixture | Malicious versions pinned | Path to the first malicious package |
|---|---|---|
| `orders-api` | `cache-manager@7.2.10` | direct dependency, 1 hop |
| `gateway` | `@cacheable/net@2.1.1`, `@cacheable/utils@2.5.1`, `keyv@6.0.0` | `@acme/http-client` then 3 more hops |
| `billing-worker` | none | locks `keyv@6.0.1`, which is not named by any real advisory |

The malicious versions come from real OSV records (see `docs/incident.md`). The package `@acme/http-client` and the
dependency edges below the malicious packages are illustrative. The lockfiles are never installed.

`billing-worker` exists for the replay's Reopen moment. At the start it is CLEARED, because `keyv@6.0.1` is not on the
advisory. A **scripted, clearly labelled** replay event later adds `keyv@6.0.1` to the advisory, which breaks exactly the
assumption its decision rested on. The event is hypothetical and is shown as such; no real advisory names that version.
