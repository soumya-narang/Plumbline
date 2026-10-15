"""Pin the repository fleet to the incident's point in time and record each lockfile's hash."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from plumbline import config
from plumbline.ingest.npm_lock import UnsupportedLockfile, parse_npm_lock

LOCKFILES = ("package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml")
NPM_LOCKFILES = {"package-lock.json", "npm-shrinkwrap.json"}
FLEET_PATH = config.DATA / "fleet.json"
INCIDENT_PATH = config.DATA / "incident.json"
CANDIDATES_PATH = config.DATA / "fleet_candidates.json"


@dataclass(frozen=True)
class FleetEntry:
    id: str  # "owner/name" for real repositories, "planted/<name>" for fixtures
    kind: str  # "real" | "planted"
    sha: str | None
    committed_at: str | None
    lockfile: str | None
    lock_state: str  # "present" | "absent" | "unsupported"
    lockfile_sha256: str | None
    note: str

    @property
    def slug(self) -> str:
        return self.id.replace("/", "__")

    @property
    def lockfile_path(self) -> Path | None:
        if self.lockfile is None:
            return None
        base = config.FIXTURES / "planted" / self.id.split("/", 1)[1] if self.kind == "planted" \
            else config.RAW / "lockfiles" / self.slug
        return base / self.lockfile


def load_incident() -> dict:
    return json.loads(INCIDENT_PATH.read_text(encoding="utf-8"))


def load_fleet() -> list[FleetEntry]:
    rows = json.loads(FLEET_PATH.read_text(encoding="utf-8"))
    return [FleetEntry(**r) for r in rows]


def commit_at(repo: str, until: str) -> tuple[str, str] | None:
    """Last commit on the default branch at or before ``until`` as ``(sha, committed_at)``.

    Uses a metadata-only shallow clone (no trees, no blobs, no checkout), so no repository content is
    written to disk or executed, and the GitHub API rate limit does not apply.
    """
    last_error = ""
    for window in ("14 days", "365 days", "1500 days"):
        with tempfile.TemporaryDirectory(dir=config.RAW) as tmp:
            clone = subprocess.run(
                ["git", "clone", "--bare", "--single-branch", "--filter=tree:0",
                 f"--shallow-since={_days_before(until, window)}", f"https://github.com/{repo}.git", tmp],
                capture_output=True, text=True, timeout=300)
            if clone.returncode != 0:
                last_error = clone.stderr.strip()[:200]
                continue  # e.g. no commits in this window; retry with a wider one
            log = subprocess.run(["git", "-C", tmp, "log", "-1", f"--before={until}", "--format=%H %cI", "HEAD"],
                                 capture_output=True, text=True, timeout=60)
            if log.stdout.strip():
                sha, committed_at = log.stdout.split()
                return sha, committed_at
    if last_error:
        raise RuntimeError(f"git clone failed for {repo}: {last_error}")
    return None


def _days_before(iso: str, window: str) -> str:
    from datetime import datetime, timedelta

    days = int(window.split()[0])
    return (datetime.fromisoformat(iso.replace("Z", "+00:00")) - timedelta(days=days)).date().isoformat()


def _pin_real(client: httpx.Client, repo: str, until: str) -> FleetEntry:
    found = commit_at(repo, until)
    if found is None:
        return FleetEntry(repo, "real", None, None, None, "absent", None, "no commit at or before as_of")
    sha, committed_at = found
    for name in LOCKFILES:
        resp = client.get(f"https://raw.githubusercontent.com/{repo}/{sha}/{name}")
        if resp.status_code != 200:
            continue
        digest = hashlib.sha256(resp.content).hexdigest()
        dest = config.RAW / "lockfiles" / repo.replace("/", "__")
        dest.mkdir(parents=True, exist_ok=True)
        (dest / name).write_bytes(resp.content)
        state, note = "present", ""
        if name not in NPM_LOCKFILES:
            state, note = "unsupported", f"{name} is not parsed by this build"
        else:
            try:
                parse_npm_lock(resp.content)
            except UnsupportedLockfile as exc:
                state, note = "unsupported", str(exc)
        return FleetEntry(repo, "real", sha, committed_at, name, state, digest, note)
    return FleetEntry(repo, "real", sha, committed_at, None, "absent", None, "no lockfile at this commit")


def _planted_entries() -> list[FleetEntry]:
    entries = []
    for lock in sorted((config.FIXTURES / "planted").glob("*/package-lock.json")):
        name = lock.parent.name
        entries.append(FleetEntry(
            id=f"planted/{name}", kind="planted", sha=None, committed_at=None,
            lockfile="package-lock.json", lock_state="present",
            lockfile_sha256=hashlib.sha256(lock.read_bytes()).hexdigest(),
            note="hand-authored fixture; dependency edges below the malicious packages are illustrative",
        ))
    return entries


def pin_fleet() -> list[FleetEntry]:
    as_of = load_incident()["as_of"]
    repos = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))["repos"]
    config.RAW.mkdir(parents=True, exist_ok=True)
    entries: list[FleetEntry] = []
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for repo in repos:
            entry = _pin_real(client, repo, as_of)
            entries.append(entry)
            print(f"{repo:30} {entry.lock_state:12} {entry.lockfile or '-':20} {(entry.sha or '-')[:10]}")
    entries.extend(_planted_entries())
    _write_fleet(entries)
    return entries


def verify_lockfile(entry: FleetEntry) -> bytes:
    """Read a pinned lockfile and check it against the recorded hash."""
    path = entry.lockfile_path
    if path is None or not path.exists():
        raise FileNotFoundError(f"missing lockfile for {entry.id}; re-run `python -m plumbline pin-fleet`")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != entry.lockfile_sha256:
        raise ValueError(f"hash mismatch for {entry.id}")
    return data


def refresh_planted() -> list[FleetEntry]:
    """Recompute only the planted entries (new or edited fixtures), keeping the pinned real repositories."""
    entries = [e for e in load_fleet() if e.kind == "real"] + _planted_entries()
    _write_fleet(entries)
    return entries


def _write_fleet(entries: list[FleetEntry]) -> None:
    payload = json.dumps([asdict(e) for e in entries], indent=1)
    FLEET_PATH.write_text(payload + "\n", encoding="utf-8")
