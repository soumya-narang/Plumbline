"""Probe candidate repositories for lockfiles and incident-package presence.

This is how the fleet in ``data/fleet.json`` was chosen. For every candidate it pins the
current default-branch commit, looks for a lockfile at that commit, and reports whether any
package from the incident appears in it. Lockfiles are fetched as inert data and are only
ever parsed, never installed or executed.

Usage:
    python scripts/probe_fleet.py            # probe the built-in candidate list
    python scripts/probe_fleet.py owner/repo ...
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "lockfiles"
REPORT = ROOT / "data" / "raw" / "fleet_probe.json"

LOCKFILES = ("package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml")
INCIDENT_PACKAGES = ("keyv", "cache-manager", "cacheable", "@cacheable/memory", "@cacheable/net",
                     "@cacheable/node-cache", "@cacheable/utils")

CANDIDATES = [
    "axios/axios", "apollographql/apollo-server", "graphql/graphql-js", "puppeteer/puppeteer",
    "serverless/serverless", "release-it/release-it", "mochajs/mocha", "lerna/lerna",
    "nestjs/nest", "typeorm/typeorm", "sequelize/sequelize", "microsoft/TypeScript",
    "microsoft/playwright", "mongodb/node-mongodb-native", "socketio/socket.io",
    "nodemailer/nodemailer", "winstonjs/winston", "cypress-io/cypress", "TypeStrong/typedoc",
    "webpack/webpack", "jestjs/jest", "prettier/prettier", "strapi/strapi", "parcel-bundler/parcel",
    "eslint/eslint", "sindresorhus/got", "expressjs/express", "fastify/fastify",
    "node-fetch/node-fetch", "Automattic/mongoose", "nodejs/undici", "npm/cli",
    "jaredwray/keyv", "jaredwray/cacheable",
]


def head_sha(repo: str) -> str | None:
    out = subprocess.run(
        ["git", "ls-remote", f"https://github.com/{repo}.git", "HEAD"],
        capture_output=True, text=True, timeout=60, check=False,
    )
    return out.stdout.split()[0] if out.returncode == 0 and out.stdout.strip() else None


def present_in_npm_lock(doc: dict) -> dict[str, list[str]]:
    found: dict[str, set[str]] = {}
    for path, meta in (doc.get("packages") or {}).items():
        name = meta.get("name") or path.rsplit("node_modules/", 1)[-1]
        if name in INCIDENT_PACKAGES and meta.get("version"):
            found.setdefault(name, set()).add(meta["version"])
    return {k: sorted(v) for k, v in found.items()}


def probe(client: httpx.Client, repo: str) -> dict:
    row: dict = {"repo": repo, "sha": None, "lockfile": None, "bytes": 0}
    sha = head_sha(repo)
    row["sha"] = sha
    if not sha:
        row["note"] = "ls-remote failed"
        return row
    for name in LOCKFILES:
        url = f"https://raw.githubusercontent.com/{repo}/{sha}/{name}"
        resp = client.get(url)
        if resp.status_code != 200:
            continue
        row.update(lockfile=name, bytes=len(resp.content))
        dest = RAW_DIR / repo.replace("/", "__")
        dest.mkdir(parents=True, exist_ok=True)
        (dest / name).write_bytes(resp.content)
        if name in ("package-lock.json", "npm-shrinkwrap.json"):
            doc = json.loads(resp.content)
            row["lockfileVersion"] = doc.get("lockfileVersion")
            row["packages"] = len(doc.get("packages") or {})
            row["incident_packages"] = present_in_npm_lock(doc)
        break
    return row


def main(argv: list[str]) -> None:
    repos = argv or CANDIDATES
    rows = []
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for repo in repos:
            row = probe(client, repo)
            rows.append(row)
            hit = ",".join(f"{k}@{'/'.join(v)}" for k, v in row.get("incident_packages", {}).items())
            print(f"{repo:36} {row['lockfile']!s:20} {row['bytes']:>9} "
                  f"v{row.get('lockfileVersion', '-')!s:<3} pkgs={row.get('packages', '-')!s:<6} {hit}")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
