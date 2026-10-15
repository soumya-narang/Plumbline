"""Export the whole incident as static JSON so the UI works with no server.

For every stop on the timeline this writes the snapshot the live API would return and the planner's answer to each
suggested question. The output is deterministic, so re-running it on unchanged data produces identical files.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from plumbline import config
from plumbline.agent.runner import ask
from plumbline.agent.suggestions import SUGGESTIONS
from plumbline.graph.client import connect
from plumbline.memory.replay import reset
from plumbline.snapshot import build_meta, snapshot

DEFAULT_OUT = config.ROOT / "web" / "data"


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _static_run(run: dict) -> dict:
    run["calls"] = [{**c, "ms": None} for c in run["calls"]]  # timings are not reproducible, so they are not recorded
    return run


def export(out_dir: Path = DEFAULT_OUT) -> int:
    graph = connect()
    meta = build_meta(graph)
    _write(out_dir / "meta.json", {**meta, "mode": "static", "agent": {"backend": "planner", "model": None}})
    for stop in meta["timeline"]:
        snap = snapshot(graph, stop["at_ms"])
        _write(out_dir / "snapshots" / f"{stop['index']}.json", snap)
        answers = {}
        for question in SUGGESTIONS:  # the graph is already positioned at this stop by snapshot()
            answers[question] = _static_run(asyncio.run(ask(question, stop["at"], backend="planner")).to_dict())
        _write(out_dir / "agent" / f"{stop['index']}.json", answers)
    reset(graph)
    return len(meta["timeline"])
