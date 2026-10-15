import json

import pytest

from plumbline.agent.suggestions import SUGGESTIONS
from plumbline.export_static import export
from plumbline.graph.client import connect
from plumbline.memory.replay import reset
from plumbline.snapshot import snapshot
from plumbline.timeutil import to_ms


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    try:
        g = connect()
        n = g.ro_query("MATCH (a:Artifact) RETURN count(a)").result_set[0][0]
    except Exception as exc:
        pytest.skip(f"FalkorDB not available: {exc}")
    if not n:
        pytest.skip("graph is empty; run `python -m plumbline load`")
    out = tmp_path_factory.mktemp("static")
    export(out)
    yield out
    reset(g)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_every_stop_has_a_snapshot_and_recorded_answers(exported):
    meta = load(exported / "meta.json")
    assert meta["mode"] == "static" and len(meta["timeline"]) == 13
    for stop in meta["timeline"]:
        assert (exported / "snapshots" / f"{stop['index']}.json").exists()
        assert set(load(exported / "agent" / f"{stop['index']}.json")) == set(SUGGESTIONS)


def test_static_snapshot_equals_the_live_one(exported):
    meta = load(exported / "meta.json")
    stop = meta["timeline"][-1]
    assert load(exported / "snapshots" / f"{stop['index']}.json") == json.loads(
        json.dumps(snapshot(connect(), to_ms(stop["at"])))
    )


def test_recorded_runs_are_deterministic_so_timings_are_not_stored(exported):
    run = next(iter(load(exported / "agent" / "12.json").values()))
    assert run["backend"] == "planner" and all(c["ms"] is None for c in run["calls"])


def test_export_is_reproducible(exported, tmp_path):
    export(tmp_path)
    for rel in ("meta.json", "snapshots/12.json", "agent/12.json"):
        assert (tmp_path / rel).read_text(encoding="utf-8") == (exported / rel).read_text(encoding="utf-8")
