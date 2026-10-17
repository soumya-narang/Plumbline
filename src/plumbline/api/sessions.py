"""Per-visitor history, and the limits that keep a public demo fair.

The graph holds one set of decision memory, and every replay move rewrites it to match the viewer's position. What
makes that safe for several visitors is that each request first rewinds the graph to *that visitor's* history (under
the app's lock) and only then reads or writes. So a visitor's approvals and what-ifs live here, keyed by a cookie,
and are replayed for that visitor alone.

Approvals are durable: they are appended to a file and reloaded at start, so a restart does not lose the decisions a
person recorded. What-ifs are deliberately temporary. They are hypothetical, and forgetting them on restart is safe.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
import time
from collections import OrderedDict
from pathlib import Path

COOKIE = "plumbline_session"
APPROVAL = "approve"
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SESSION = re.compile(r"^[0-9a-f]{32}$")
_APPROVAL_FIELDS = ("at", "type", "advisory", "artifact", "approver", "manual")


class Refused(Exception):
    """A request the demo declines to serve; the message is safe to show."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def clean_name(raw: str) -> str:
    name = " ".join(_CONTROL.sub(" ", raw).split())[:80]
    if not name:
        raise Refused("enter a name to record who approved this")
    return name


def state_file() -> Path | None:
    """Where approvals are kept: ``$PLUMBLINE_STATE_DIR/approvals.jsonl``, or ``data/state`` in the project.
    Set ``PLUMBLINE_STATE_DIR=off`` to keep everything in memory only."""
    from plumbline import config

    raw = os.getenv("PLUMBLINE_STATE_DIR")
    if raw and raw.lower() == "off":
        return None
    return (Path(raw) if raw else config.DATA / "state") / "approvals.jsonl"


class Approvals:
    def __init__(self, max_sessions: int = 200, max_per_session: int = 20, per_hour: int = 10, enabled: bool = True,
                 path: Path | None = None):
        self.max_sessions, self.max_per_session, self.per_hour, self.enabled = max_sessions, max_per_session, per_hour, enabled
        self._by_session: OrderedDict[str, list[dict]] = OrderedDict()
        self._recent: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self._path = path
        if path is not None:
            self._load()

    # ------------------------------------------------------------ durability

    @staticmethod
    def _valid(session: object, event: object) -> bool:
        return (isinstance(session, str) and bool(_SESSION.match(session)) and isinstance(event, dict)
                and event.get("type") == APPROVAL
                and all(isinstance(event.get(k), str) for k in ("at", "advisory", "artifact", "approver")))

    def _load(self) -> None:
        """Rebuild from the file, ignoring anything malformed, then rewrite it compactly so it cannot grow without bound."""
        if self._path is None or not self._path.exists():
            return
        for line in self._path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            session, event = row.get("session"), row.get("event")
            if not self._valid(session, event):
                continue
            events = self._by_session.setdefault(session, [])
            if len(events) < self.max_per_session:
                events.append({k: event[k] for k in _APPROVAL_FIELDS if k in event})
            self._by_session.move_to_end(session)
        while len(self._by_session) > self.max_sessions:
            self._by_session.popitem(last=False)
        self._rewrite()

    def _rewrite(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            for session, events in self._by_session.items():
                for e in events:
                    if e.get("type") == APPROVAL:
                        f.write(json.dumps({"session": session, "event": e}, sort_keys=True) + "\n")
        tmp.replace(self._path)

    def _append(self, session: str, event: dict) -> None:
        if self._path is None or event.get("type") != APPROVAL:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"session": session, "event": event}, sort_keys=True) + "\n")
            f.flush()

    # ---------------------------------------------------------------- state

    @staticmethod
    def new_session() -> str:
        return secrets.token_hex(16)

    def history(self, session: str) -> list[dict]:
        with self._lock:
            events = self._by_session.get(session, [])
            if session in self._by_session:
                self._by_session.move_to_end(session)
            return list(events)

    def digest(self, session: str) -> str:
        """Identifies a visitor's history, so cached snapshots are never shared between different histories."""
        events = self.history(session)
        return hashlib.sha256(json.dumps(events, sort_keys=True).encode()).hexdigest()[:16] if events else ""

    def check_allowed(self, session: str, client: str) -> None:
        """Raise Refused when approvals are switched off or this visitor has used up its share."""
        if not self.enabled:
            raise Refused("approvals are switched off on this deployment; the recorded decisions are shown read-only", 403)
        now = time.time()
        with self._lock:
            recent = [t for t in self._recent.get(client, []) if now - t < 3600]
            self._recent[client] = recent
            if len(recent) >= self.per_hour:
                raise Refused(f"at most {self.per_hour} approvals or what-ifs per hour from one address", 429)
            if len(self._by_session.get(session, [])) >= self.max_per_session:
                raise Refused(f"a session can hold at most {self.max_per_session} approvals and what-ifs", 429)

    def clear_what_ifs(self, session: str) -> None:
        """Forget this visitor's hypothetical revisions. Approvals are decisions and are kept."""
        with self._lock:
            kept = [e for e in self._by_session.get(session, []) if e.get("type") == APPROVAL]
            if kept:
                self._by_session[session] = kept
            else:
                self._by_session.pop(session, None)

    def add(self, session: str, client: str, event: dict) -> None:
        with self._lock:
            self._by_session.setdefault(session, []).append(event)
            self._by_session.move_to_end(session)
            dropped = False
            while len(self._by_session) > self.max_sessions:
                self._by_session.popitem(last=False)
                dropped = True
            self._recent.setdefault(client, []).append(time.time())
            if dropped:
                self._rewrite()
            else:
                self._append(session, event)
