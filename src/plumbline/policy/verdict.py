"""Deterministic verdict policy.

Pure functions over plain data, with no database and no language model. A verdict is only ever produced
here, so every EXPOSED, CLEARED or UNKNOWN can be unit-tested and re-derived from the same inputs.

Verdicts
    EXPOSED  the artifact's lockfile pins a version the advisory names as affected
    CLEARED  the lockfile is present and pins no affected version; valid only relative to the
             assumptions returned with the verdict (they are what a later fact can break)
    UNKNOWN  the evidence needed to decide is missing, so the policy refuses to guess

Priority (service exposure, tier) orders EXPOSED results elsewhere and never changes a verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Verdict = Literal["EXPOSED", "CLEARED", "UNKNOWN"]
POLICY_VERSION = "1"


@dataclass(frozen=True)
class Locked:
    """One concrete package version an artifact's lockfile pins."""

    purl: str
    name: str
    version: str
    depth: int | None
    dev: bool = False


@dataclass(frozen=True)
class ArtifactState:
    id: str
    lock_state: str  # "present" | "absent" | "unsupported"
    lock_sha256: str | None
    locked: tuple[Locked, ...]


@dataclass(frozen=True)
class AdvisoryState:
    id: str
    package: str
    affected_purls: frozenset[str]


@dataclass(frozen=True)
class Assumption:
    """A fact a CLEARED verdict rests on. If it stops being true, the decision must reopen."""

    kind: Literal["lock_snapshot", "not_affected"]
    key: str  # lock_snapshot: the lockfile hash; not_affected: the purl the advisory does not name

    @property
    def fact_id(self) -> str:
        return f"{self.kind}:{self.key}"


@dataclass(frozen=True)
class Result:
    verdict: Verdict
    reason: str
    evidence: tuple[Locked, ...]
    assumptions: tuple[Assumption, ...]


def evaluate(artifact: ArtifactState, advisory: AdvisoryState) -> Result:
    if artifact.lock_state == "absent":
        return Result("UNKNOWN", "no_lockfile", (), ())
    if artifact.lock_state != "present":
        return Result("UNKNOWN", "lockfile_format_unsupported", (), ())

    hits = tuple(sorted((x for x in artifact.locked if x.purl in advisory.affected_purls), key=lambda x: x.purl))
    if hits:
        return Result("EXPOSED", "affected_version_locked", hits, ())

    same_package = tuple(sorted((x for x in artifact.locked if x.name == advisory.package), key=lambda x: x.purl))
    # A lockfile hash is part of every assumption set: if the lockfile changes, nothing here still holds.
    assumptions = [Assumption("lock_snapshot", artifact.lock_sha256 or "")]
    assumptions += [Assumption("not_affected", f"{advisory.id}:{x.purl}") for x in same_package]
    reason = "safe_version_locked" if same_package else "package_absent"
    return Result("CLEARED", reason, same_package, tuple(assumptions))
