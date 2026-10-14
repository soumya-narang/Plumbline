"""Paths and environment-driven settings shared across the package."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
FIXTURES = DATA / "fixtures"
QUERIES = ROOT / "queries"

load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    falkordb_host: str
    falkordb_port: int
    falkordb_password: str | None


def load_settings() -> Settings:
    return Settings(
        falkordb_host=os.getenv("FALKORDB_HOST", "localhost"),
        falkordb_port=int(os.getenv("FALKORDB_PORT", "6390")),
        falkordb_password=os.getenv("FALKORDB_PASSWORD") or None,
    )
