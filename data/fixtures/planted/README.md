# Planted fixtures

Two hand-authored lockfiles, labelled synthetic everywhere they appear. They exist so the demo can show an
EXPOSED verdict without making any claim about a real third-party repository.

| Fixture | Malicious versions pinned | Path to the first malicious package |
|---|---|---|
| `orders-api` | `cache-manager@7.2.10` | direct dependency, 1 hop |
| `gateway` | `@cacheable/net@2.1.1`, `@cacheable/utils@2.5.1`, `keyv@6.0.0` | `@acme/http-client` then 3 more hops |

The malicious versions come from real OSV records (see `docs/incident.md`). The package `@acme/http-client` and the
dependency edges below the malicious packages are illustrative. The lockfiles are never installed.
