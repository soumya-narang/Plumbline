"""Small helpers for converting between ISO-8601 timestamps and epoch milliseconds."""

from __future__ import annotations

from datetime import datetime, timezone


def to_ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def to_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)
