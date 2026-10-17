"""Per-visitor approval history, and the limits that keep a public demo fair.

The graph holds one set of decision memory, and every replay move rewrites it to match the viewer's position. What
makes that safe for several visitors is that each request first rewinds the graph to *that visitor's* history (under
the app's lock) and only then reads or writes. So a visitor's approvals live here, keyed by a cookie, and are replayed
for that visitor alone.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import time
from collections import OrderedDict

COOKIE = "plumbline_session"
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


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


class Approvals:
    def __init__(self, max_sessions: int = 200, max_per_session: int = 20, per_hour: int = 10, enabled: bool = True):
        self.max_sessions, self.max_per_session, self.per_hour, self.enabled = max_sessions, max_per_session, per_hour, enabled
        self._by_session: OrderedDict[str, list[dict]] = OrderedDict()
        self._recent: dict[str, list[float]] = {}
        self._lock = threading.Lock()

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

    def clear(self, session: str) -> None:
        with self._lock:
            self._by_session.pop(session, None)

    def add(self, session: str, client: str, event: dict) -> None:
        with self._lock:
            self._by_session.setdefault(session, []).append(event)
            self._by_session.move_to_end(session)
            while len(self._by_session) > self.max_sessions:
                self._by_session.popitem(last=False)
            self._recent.setdefault(client, []).append(time.time())
