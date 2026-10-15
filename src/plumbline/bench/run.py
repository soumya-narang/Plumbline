"""Run the ablation: the graph, SQL and naive retrieval, graded against npm's own resolver.

Questions (all about the pinned lockfiles of the incident fleet):
  locks       does artifact A lock package P at version V?                  single hop
  pulled_by   which direct dependencies of A pull P@V in, however deep?     multi hop
  fleet       which artifacts in the whole fleet lock P@V?                  fleet wide

Gold answers come from ``npm ls`` run offline against each lockfile, so they do not depend on this project's parser,
graph or policy. Artifacts the oracle cannot read (workspaces, or no readable lockfile) are excluded and listed.
"""

from __future__ import annotations

import json
import platform
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from plumbline import config
from plumbline.bench.oracle import npm_available, npm_ls, npm_version, unsupported_reason
from plumbline.bench.systems import GraphSystem, RetrievalSystem, SqlSystem, load_facts
from plumbline.graph.client import connect
from plumbline.ingest.fleet import FleetEntry, load_fleet, verify_lockfile

TARGETS = [
    ("keyv", "6.0.0"), ("keyv", "5.6.0"), ("keyv", "4.5.4"),
    ("cache-manager", "7.2.9"), ("cache-manager", "7.2.10"),
    ("@cacheable/utils", "2.5.0"), ("@cacheable/utils", "2.5.1"),
]
REPEATS = 3
RESULT_JSON = config.ROOT / "docs" / "benchmark.json"
RESULT_MD = config.ROOT / "docs" / "benchmark.md"
SITE_JSON = config.ROOT / "web" / "data" / "benchmark.json"


@dataclass(frozen=True)
class Question:
    kind: str  # locks | pulled_by | fleet
    artifact: str | None
    name: str
    version: str


def build_gold(entries: list[FleetEntry]):
    """Gold answers from npm, plus the artifacts that could not be graded and why."""
    locks: dict[tuple, bool] = {}
    pulled: dict[tuple, set[str]] = {}
    graded: list[str] = []
    skipped: dict[str, str] = {}
    names = sorted({n for n, _ in TARGETS})
    for e in entries:
        if e.lock_state != "present":
            skipped[e.id] = f"lockfile {e.lock_state}"
            continue
        data = verify_lockfile(e)
        reason = unsupported_reason(data)
        if reason:
            skipped[e.id] = reason
            continue
        graded.append(e.id)
        for name in names:
            found = npm_ls(data, name)
            for n, v in TARGETS:
                if n == name:
                    locks[(e.id, n, v)] = v in found
                    pulled[(e.id, n, v)] = set(found.get(v, set()))
    return locks, pulled, graded, skipped


def build_questions(graded: list[str], locks: dict) -> list[Question]:
    qs = [Question("locks", a, n, v) for a in graded for n, v in TARGETS]
    qs += [Question("pulled_by", a, n, v) for a in graded for n, v in TARGETS if locks[(a, n, v)]]
    qs += [Question("fleet", None, n, v) for n, v in TARGETS]
    return qs


def ask(system, q: Question, graded: set[str]):
    if q.kind == "locks":
        return system.locks(q.artifact, q.name, q.version)
    if q.kind == "pulled_by":
        return system.pulled_by(q.artifact, q.name, q.version)
    return system.fleet(q.name, q.version) & graded  # grade only the artifacts the oracle can read


def gold_for(q: Question, locks: dict, pulled: dict, graded: list[str]):
    if q.kind == "locks":
        return locks[(q.artifact, q.name, q.version)]
    if q.kind == "pulled_by":
        return pulled[(q.artifact, q.name, q.version)]
    return {a for a in graded if locks[(a, q.name, q.version)]}


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(p * (len(ordered) - 1)))]


def evaluate(system, questions, gold, graded_set):
    per_kind: dict[str, dict] = {}
    failures: list[dict] = []
    for q in questions:
        samples = []
        answer = None
        for _ in range(REPEATS):
            t = time.perf_counter()
            answer = ask(system, q, graded_set)
            samples.append((time.perf_counter() - t) * 1000)
        ok = answer == gold[q]
        bucket = per_kind.setdefault(q.kind, {"n": 0, "correct": 0, "ms": []})
        bucket["n"] += 1
        bucket["correct"] += int(ok)
        bucket["ms"].append(statistics.median(samples))
        if not ok and len(failures) < 6:
            failures.append({"kind": q.kind, "artifact": q.artifact, "target": f"{q.name}@{q.version}",
                             "expected": sorted(gold[q]) if isinstance(gold[q], set) else gold[q],
                             "answered": sorted(answer) if isinstance(answer, set) else answer})
    out = {}
    for kind, b in per_kind.items():
        out[kind] = {"questions": b["n"], "correct": b["correct"], "accuracy": round(b["correct"] / b["n"], 4),
                     "p50_ms": round(percentile(b["ms"], 0.5), 3), "p95_ms": round(percentile(b["ms"], 0.95), 3)}
    return out, failures


def run() -> dict:
    if not npm_available():
        raise SystemExit("npm is required: it is the independent oracle for the ablation")
    entries = load_fleet()
    locks, pulled, graded, skipped = build_gold(entries)
    questions = build_questions(graded, locks)
    gold = {q: gold_for(q, locks, pulled, graded) for q in questions}
    graded_set = set(graded)

    deps, edges = load_facts([e for e in entries if e.lock_state == "present"])
    systems = [GraphSystem(connect()), SqlSystem(deps, edges, "reverse"), SqlSystem(deps, edges, "forward"), RetrievalSystem(deps, edges)]
    results, failures, query_lines = {}, {}, {}
    for s in systems:
        ask(s, questions[0], graded_set)  # warm up
        results[s.name], failures[s.name] = evaluate(s, questions, gold, graded_set)
        query_lines[s.name] = s.query_lines()

    return {
        "generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "machine": {"platform": platform.platform(), "python": sys.version.split()[0]},
        "oracle": {"tool": "npm ls --package-lock-only --offline", "npm": npm_version()},
        "questions": {k: sum(1 for q in questions if q.kind == k) for k in ("locks", "pulled_by", "fleet")},
        "targets": [f"{n}@{v}" for n, v in TARGETS],
        "artifacts_graded": graded,
        "artifacts_skipped": skipped,
        "results": results,
        "query_lines": query_lines,
        "failures": failures,
        "repeats_per_question": REPEATS,
    }


def render_markdown(r: dict) -> str:
    kinds = [("locks", "Does A lock P@V? (single hop)"), ("pulled_by", "Which direct dependencies pull P@V in? (multi hop)"),
             ("fleet", "Which artifacts lock P@V? (fleet wide)")]
    skipped = ", ".join(f"{a} ({why})" for a, why in r["artifacts_skipped"].items())
    intro = (
        f"Generated {r['generated']} on {r['machine']['platform']} with Python {r['machine']['python']}. "
        f"Gold answers come from `{r['oracle']['tool']}` (npm {r['oracle']['npm']}), "
        "which does not use this project's parser, graph or policy."
    )
    lines = [
        "# Ablation: graph, SQL and naive retrieval", "", intro, "",
        f"{len(r['artifacts_graded'])} artifacts were graded; {len(r['artifacts_skipped'])} were excluded: {skipped}.", "",
        "| Question | Questions | Graph (FalkorDB) | SQL, tuned (SQLite) | SQL, first attempt | Retrieval (BM25) |",
        "|---|---|---|---|---|---|",
    ]
    for key, label in kinds:
        cells = []
        for system in ("graph", "sql", "sql_forward", "retrieval"):
            res = r["results"][system][key]
            cells.append(f"{res['correct']}/{res['questions']} ({res['accuracy']:.0%}), p50 {res['p50_ms']} ms")
        lines.append(f"| {label} | {r['questions'][key]} | " + " | ".join(cells) + " |")
    ql = r["query_lines"]
    size = (
        "Non-comment lines of query for the multi-hop question: "
        f"Cypher {ql['graph']['pulled_by']}, tuned SQL {ql['sql']['pulled_by']}, "
        f"first-attempt SQL {ql['sql_forward']['pulled_by']} (both recursive)."
    )
    caveat = (
        "Latency is the median of three runs per question, on one machine, with FalkorDB reached over a local socket; "
        "treat it as indicative, not a benchmark claim."
    )
    lines += ["", size, "", caveat]
    for system, fails in r["failures"].items():
        if fails:
            lines += ["", f"First wrong answers from {system}:", "", "```json", json.dumps(fails[:3], indent=1), "```"]
    return "\n".join(lines) + "\n"


def main() -> None:
    result = run()
    payload = json.dumps(result, indent=1, sort_keys=True) + "\n"
    for path in (RESULT_JSON, SITE_JSON):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8", newline="\n")
    RESULT_MD.write_text(render_markdown(result), encoding="utf-8", newline="\n")
    print(render_markdown(result))


if __name__ == "__main__":
    main()
