"""Derive the planted `storefront` fixture from a real lockfile.

The haystack is the real, pinned lockfile of a public project (axios at the incident time), renamed and given one extra
direct dependency. That dependency, a fictional `@acme/payments-sdk`, pulls in the malicious versions of the campaign
through a nested chain. Everything is labelled synthetic wherever it appears; the result is never installed.

Usage: python scripts/make_storefront_fixture.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "raw" / "lockfiles" / "axios__axios" / "package-lock.json"
TARGET = ROOT / "data" / "fixtures" / "planted" / "storefront" / "package-lock.json"

SDK = "node_modules/@acme/payments-sdk"


def main() -> None:
    lock = json.loads(SOURCE.read_text(encoding="utf-8"))
    packages = lock["packages"]
    root = packages[""]
    root["name"], root["version"] = "storefront", "4.2.0"
    root.setdefault("dependencies", {})["@acme/payments-sdk"] = "^2.1.0"
    lock["name"], lock["version"] = "storefront", "4.2.0"

    # The injected chain: payments-sdk -> @cacheable/net -> @cacheable/utils -> keyv, all malicious versions, nested so
    # that they are separate installs from the safe copies elsewhere in the tree.
    packages[SDK] = {"version": "2.1.0", "dependencies": {"@cacheable/net": "^2.1.0"}}
    packages[f"{SDK}/node_modules/@cacheable/net"] = {"version": "2.1.1", "dependencies": {"@cacheable/utils": "^2.5.0"}}
    packages[f"{SDK}/node_modules/@cacheable/utils"] = {"version": "2.5.1", "dependencies": {"keyv": "^6.0.0"}}
    packages[f"{SDK}/node_modules/keyv"] = {"version": "6.0.0"}

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {TARGET.relative_to(ROOT)} with {len(packages)} packages")


if __name__ == "__main__":
    main()
