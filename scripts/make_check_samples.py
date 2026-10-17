"""Write the sample lockfiles offered on the check page (web/samples/).

Three files that between them cover the verdicts the checker can give:
  - a hand-authored lockfile where the poisoned keyv release is three levels down,
  - a real, unmodified lockfile (nodemailer) that locks a safe keyv,
  - that same real lockfile with one line changed so keyv resolves to the poisoned release.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "samples"
POISONED = "6.0.0"


def write(name: str, data: dict | bytes) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    body = data if isinstance(data, bytes) else (json.dumps(data, indent=2) + "\n").encode("utf-8")
    (OUT / name).write_bytes(body.replace(b"\r\n", b"\n"))


def main() -> None:
    write("exposed-hand-authored.json", (ROOT / "data/fixtures/planted/gateway/package-lock.json").read_bytes())

    real = (ROOT / "data/raw/lockfiles/nodemailer__nodemailer/package-lock.json").read_bytes()
    write("clear-real-nodemailer.json", real)

    edited = json.loads(real)
    entry = edited["packages"]["node_modules/keyv"]
    print(f"nodemailer locks keyv@{entry['version']}; the edited sample sets it to {POISONED}")
    entry["version"] = POISONED
    write("exposed-real-nodemailer-edited.json", edited)


if __name__ == "__main__":
    main()
