"""Small helpers for converting between ISO-8601 timestamps and epoch milliseconds."""

from __future__ import annotations

from datetime import UTC, datetime


def to_ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp() * 1000)


def to_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_ms() -> int:
    return int(datetime.now(tz=UTC).timestamp() * 1000)
