"""Replay the incident: apply recorded approvals and labelled scripted events in time order.

``seek`` is deterministic and idempotent. It wipes everything the replay writes, then re-applies every event up to
the requested time, so a slider can move backwards as well as forwards.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from falkordb import Graph

from plumbline import config
from plumbline.graph.client import run_named
from plumbline.ingest.npm_lock import parse_purl
from plumbline.memory.decisions import Reopened, commit, list_decisions, propose, reopen
from plumbline.timeutil import to_ms

REPLAY_PATH = config.DATA / "replay.json"
REPLAY_APPROVER = "replay"


@dataclass(frozen=True)
class ReplayState:
    at_ms: int
    applied: tuple[dict, ...]
    decisions: tuple[dict, ...]
    reopened: tuple[Reopened, ...]


def load_events(extra: list[dict] | None = None) -> list[dict]:
    """Recorded events plus any extra (for example manual approvals), ordered by time."""
    events = json.loads(REPLAY_PATH.read_text(encoding="utf-8"))["events"] + list(extra or [])
    return sorted(({**e, "at_ms": to_ms(e["at"])} for e in events), key=lambda e: e["at_ms"])


def reset(graph: Graph) -> None:
    run_named(graph, "memory/reset_memory", read_only=False)
    run_named(graph, "memory/reset_scripted_edges", read_only=False)


def _apply_revision(graph: Graph, event: dict) -> None:
    rows = []
    for purl in event["add_purls"]:
        name, version = parse_purl(purl)
        rows.append({"purl": purl, "name": name, "version": version})
    run_named(graph, "memory/apply_revision",
              {"advisory": event["advisory"], "at_ms": event["at_ms"], "rows": rows}, read_only=False)


def seek(graph: Graph, at_ms: int, extra: list[dict] | None = None) -> ReplayState:
    reset(graph)
    applied: list[dict] = []
    reopened: list[Reopened] = []
    for event in load_events(extra):
        if event["at_ms"] > at_ms:
            break
        if event["type"] == "approve":
            approver = event.get("approver", REPLAY_APPROVER)
            commit(graph, propose(graph, event["advisory"], event["artifact"], event["at_ms"]), approver)
        elif event["type"] == "advisory_revised":
            _apply_revision(graph, event)
        else:
            raise ValueError(f"unknown replay event type: {event['type']!r}")
        applied.append(event)
        reopened.extend(reopen(graph, event["at_ms"]))
    return ReplayState(at_ms, tuple(applied), tuple(list_decisions(graph)), tuple(reopened))
