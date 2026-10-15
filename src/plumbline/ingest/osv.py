"""Fetch the incident's malicious-package advisories from OSV and normalise them to JSONL."""

from __future__ import annotations

import json
from datetime import datetime

import httpx

from plumbline import config
from plumbline.ingest.fleet import load_incident
from plumbline.ingest.npm_lock import parse_purl, purl_for

OSV_VULN_URL = "https://api.osv.dev/v1/vulns/{id}"
ADVISORIES_PATH = config.PROCESSED / "advisories.jsonl"


def _to_ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp() * 1000)


def normalise(record: dict) -> dict:
    """One OSV record -> one row per advisory, with an explicit list of affected purls."""
    affected = record["affected"]
    purls = sorted({purl_for(a["package"]["name"], v) for a in affected for v in a.get("versions", [])})
    return {
        "id": record["id"],
        "kind": "MAL" if record["id"].startswith("MAL-") else "VULN",
        "package": affected[0]["package"]["name"],
        "summary": record.get("summary", ""),
        "published": record["published"],
        "published_ms": _to_ms(record["published"]),
        "purls": purls,
        "affected": [{"purl": p, "name": parse_purl(p)[0], "version": parse_purl(p)[1]} for p in purls],
    }


def fetch_advisories() -> list[dict]:
    ids = load_incident()["advisories"]
    rows = []
    with httpx.Client(timeout=30) as client:
        for vid in ids:
            resp = client.get(OSV_VULN_URL.format(id=vid))
            resp.raise_for_status()
            rows.append(normalise(resp.json()))
    rows.sort(key=lambda r: (r["published_ms"], r["id"]))
    config.PROCESSED.mkdir(parents=True, exist_ok=True)
    ADVISORIES_PATH.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8", newline="\n")
    return rows


def load_advisories() -> list[dict]:
    return [json.loads(line) for line in ADVISORIES_PATH.read_text(encoding="utf-8").splitlines() if line]
