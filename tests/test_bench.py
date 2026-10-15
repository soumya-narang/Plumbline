"""The ablation's baselines, on the small gateway fixture (no npm needed for these)."""

import pytest

from plumbline.bench.oracle import _walk, unsupported_reason
from plumbline.bench.run import percentile
from plumbline.bench.systems import RetrievalSystem, SqlSystem, load_facts
from plumbline.ingest.fleet import load_fleet


@pytest.fixture(scope="module")
def facts():
    entries = [e for e in load_fleet() if e.id in ("planted/gateway", "planted/orders-api")]
    return load_facts(entries)


def test_sql_variants_agree_and_find_the_direct_dependency_behind_a_four_hop_chain(facts):
    reverse = SqlSystem(*facts, strategy="reverse")
    forward = SqlSystem(*facts, strategy="forward")
    assert reverse.pulled_by("planted/gateway", "keyv", "6.0.0") == {"@acme/http-client"}
    assert forward.pulled_by("planted/gateway", "keyv", "6.0.0") == {"@acme/http-client"}
    assert reverse.locks("planted/gateway", "keyv", "6.0.0") and not reverse.locks("planted/gateway", "keyv", "5.6.0")


def test_retrieval_answers_single_hop_questions_but_runs_out_of_rounds_on_a_deep_chain(facts):
    retrieval = RetrievalSystem(*facts)
    assert retrieval.locks("planted/gateway", "keyv", "6.0.0")
    assert not retrieval.locks("planted/orders-api", "keyv", "6.0.0")
    # keyv sits four hops below the direct dependency; two retrieval rounds cannot reach it
    assert retrieval.pulled_by("planted/gateway", "keyv", "6.0.0") == set()
    # but a direct dependency is found at once
    assert retrieval.pulled_by("planted/orders-api", "cache-manager", "7.2.10") == {"cache-manager"}


def test_fleet_question_names_every_artifact_that_locks_the_version(facts):
    assert SqlSystem(*facts).fleet("keyv", "6.0.0") == {"planted/gateway"}


def test_oracle_walk_collects_the_top_level_branch_for_each_version():
    tree = {
        "a": {"version": "1", "dependencies": {"b": {"version": "1", "dependencies": {"keyv": {"version": "4.5.4"}}}}},
        "c": {"version": "1", "dependencies": {"keyv": {"version": "5.6.0"}}},
    }
    out: dict[str, set[str]] = {}
    _walk(tree, "keyv", None, out)
    assert out == {"4.5.4": {"a"}, "5.6.0": {"c"}}


def test_workspace_lockfiles_are_declared_unsupported_by_the_oracle():
    assert unsupported_reason(b'{"packages": {"": {"workspaces": ["packages/*"]}}}') == "uses workspaces"
    assert unsupported_reason(b'{"packages": {"": {}}}') is None


def test_percentile_picks_a_rank():
    assert percentile([1, 2, 3, 4, 5], 0.5) == 3
    assert percentile([1, 2, 3, 4, 5], 0.95) == 5
