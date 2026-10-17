"""Show agents passing work through the graph: one triage agent, several remediation agents, no shared memory but the graph.

The triage agent finds every EXPOSED artifact at a moment in time and hands each fix to the queue. The remediation
agents then run at the same time, each claiming tasks until none are left and completing what it claimed. The summary
says whether every task was worked exactly once, which is the property that makes the queue safe to share.
"""

from __future__ import annotations

import concurrent.futures

from falkordb import Graph

from plumbline.memory import tasks
from plumbline.snapshot import advisories_at
from plumbline.triage.engine import triage_advisory


def run_demo(graph: Graph, at_ms: int, workers: int = 4, round_name: str = "first") -> dict:
    """Hand off every exposure at ``at_ms``, then let ``workers`` agents drain the queue concurrently."""
    handed = []
    skipped_hypothetical = 0
    for adv in advisories_at(graph, at_ms):
        for v in triage_advisory(graph, adv["id"], at_ms).verdicts:
            if v.result.verdict != "EXPOSED":
                continue
            try:
                handed.append(tasks.hand_off(graph, adv["id"], v.artifact, at_ms, by="triage-agent"))
            except tasks.WorkError as exc:
                if "hypothetical" not in str(exc):
                    raise
                skipped_hypothetical += 1

    def worker(name: str) -> list[dict]:
        done = []
        while (got := tasks.claim(graph, name))["task"]:
            task = got["task"]
            done.append(tasks.complete(graph, task["id"], name, f"{round_name} round: bumped {task['fix']}") | {"claimed": task["id"]})
        return done

    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        per_worker = dict(zip((f"remediation-{i + 1}" for i in range(workers)), pool.map(worker, (f"remediation-{i + 1}" for i in range(workers))), strict=True))

    claimed = [d["claimed"] for done in per_worker.values() for d in done]
    new_tasks = [h for h in handed if h["created"]]
    return {
        "handed_off": len(handed), "newly_queued": len(new_tasks), "skipped_hypothetical": skipped_hypothetical,
        "recalled_playbooks": sorted({h["recalled"]["resolution"] for h in handed if h["recalled"]}),
        "per_worker": {name: len(done) for name, done in per_worker.items()},
        "claimed": len(claimed), "claimed_twice": len(claimed) - len(set(claimed)),
        "exactly_once": len(claimed) == len(set(claimed)) and set(claimed) >= {h["task"] for h in new_tasks},
    }
