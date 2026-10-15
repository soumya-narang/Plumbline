import pytest

from plumbline.policy.verdict import AdvisoryState, ArtifactState, Assumption, Locked, evaluate

BAD = "pkg:npm/keyv@6.0.0"
ADVISORY = AdvisoryState("MAL-1", "keyv", frozenset({BAD}))


def locked(version: str, depth: int = 2, dev: bool = False) -> Locked:
    return Locked(f"pkg:npm/keyv@{version}", "keyv", version, depth, dev)


def artifact(*locks: Locked, state: str = "present") -> ArtifactState:
    return ArtifactState("o/r", state, "abc123", tuple(locks))


def test_affected_version_is_exposed_with_evidence():
    r = evaluate(artifact(locked("6.0.0", depth=4)), ADVISORY)
    assert r.verdict == "EXPOSED" and r.reason == "affected_version_locked"
    assert [x.purl for x in r.evidence] == [BAD]
    assert r.assumptions == (Assumption("lock_snapshot", "abc123"),)  # valid only for this lockfile


def test_dev_only_exposure_is_still_exposed():
    assert evaluate(artifact(locked("6.0.0", dev=True)), ADVISORY).verdict == "EXPOSED"


def test_exposed_wins_even_if_a_safe_version_is_also_locked():
    r = evaluate(artifact(locked("4.5.4"), locked("6.0.0")), ADVISORY)
    assert r.verdict == "EXPOSED"
    assert [x.version for x in r.evidence] == ["6.0.0"]


def test_safe_version_is_cleared_and_states_what_it_assumes():
    r = evaluate(artifact(locked("4.5.4"), locked("5.6.0")), ADVISORY)
    assert r.verdict == "CLEARED" and r.reason == "safe_version_locked"
    assert r.assumptions[0] == Assumption("lock_snapshot", "abc123")
    assert {a.key for a in r.assumptions if a.kind == "not_affected"} == {
        "MAL-1:pkg:npm/keyv@4.5.4", "MAL-1:pkg:npm/keyv@5.6.0"}


def test_absent_package_is_cleared_relative_to_the_lockfile_only():
    r = evaluate(artifact(Locked("pkg:npm/pino@9.5.0", "pino", "9.5.0", 1)), ADVISORY)
    assert r.verdict == "CLEARED" and r.reason == "package_absent"
    assert r.assumptions == (Assumption("lock_snapshot", "abc123"),)


@pytest.mark.parametrize("state,reason", [("absent", "no_lockfile"), ("unsupported", "lockfile_format_unsupported")])
def test_missing_evidence_is_unknown_never_cleared(state, reason):
    r = evaluate(artifact(state=state), ADVISORY)
    assert r.verdict == "UNKNOWN" and r.reason == reason
    assert r.assumptions == ()


def test_unknown_even_when_no_locked_data_would_otherwise_look_clean():
    assert evaluate(ArtifactState("o/r", "absent", None, ()), ADVISORY).verdict == "UNKNOWN"


def test_policy_is_deterministic():
    a = artifact(locked("4.5.4"), locked("6.0.0"))
    assert evaluate(a, ADVISORY) == evaluate(a, ADVISORY)


def test_fact_ids_are_stable_and_distinct_per_kind():
    assert Assumption("lock_snapshot", "abc").fact_id == "lock_snapshot:abc"
    assert Assumption("not_affected", "MAL-1:pkg:npm/keyv@4.5.4").fact_id == "not_affected:MAL-1:pkg:npm/keyv@4.5.4"
