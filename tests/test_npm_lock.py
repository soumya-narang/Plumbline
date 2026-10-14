import json

import pytest

from plumbline.ingest.npm_lock import UnsupportedLockfile, parse_npm_lock, purl_for


def lock(packages: dict) -> str:
    return json.dumps({"lockfileVersion": 3, "packages": packages})


BASIC = {
    "": {"dependencies": {"a": "^1", "b": "^1"}, "devDependencies": {"t": "^1"}},
    "node_modules/a": {"version": "1.0.0", "dependencies": {"c": "^2"}},
    "node_modules/a/node_modules/c": {"version": "2.0.0"},
    "node_modules/b": {"version": "1.0.0", "dependencies": {"c": "^1"}},
    "node_modules/c": {"version": "1.0.0"},
    "node_modules/t": {"version": "1.0.0", "dev": True},
}


def keys(edges):
    return set(edges)


def test_nested_dependency_wins_over_hoisted():
    g = parse_npm_lock(lock(BASIC))
    assert ("node_modules/a", "node_modules/a/node_modules/c") in keys(g.edges)
    assert ("node_modules/a", "node_modules/c") not in keys(g.edges)


def test_falls_back_to_hoisted_when_not_nested():
    g = parse_npm_lock(lock(BASIC))
    assert ("node_modules/b", "node_modules/c") in keys(g.edges)


def test_direct_flags_and_depths():
    g = parse_npm_lock(lock(BASIC))
    assert g.deps["node_modules/a"].direct and g.deps["node_modules/a"].depth == 1
    assert not g.deps["node_modules/c"].direct
    assert g.deps["node_modules/c"].depth == 2
    assert g.deps["node_modules/a/node_modules/c"].depth == 2


def test_dev_dependency_is_flagged():
    g = parse_npm_lock(lock(BASIC))
    assert g.deps["node_modules/t"].dev is True
    assert g.deps["node_modules/a"].dev is False


def test_scoped_name_and_purl_encoding():
    g = parse_npm_lock(lock({
        "": {"dependencies": {"@cacheable/memory": "^2"}},
        "node_modules/@cacheable/memory": {"version": "2.2.1"},
    }))
    dep = g.deps["node_modules/@cacheable/memory"]
    assert dep.name == "@cacheable/memory"
    assert dep.purl == "pkg:npm/%40cacheable/memory@2.2.1" == purl_for("@cacheable/memory", "2.2.1")


def test_scoped_parent_walks_up_correctly():
    g = parse_npm_lock(lock({
        "": {"dependencies": {"@s/p": "1"}},
        "node_modules/@s/p": {"version": "1.0.0", "dependencies": {"x": "1"}},
        "node_modules/x": {"version": "1.0.0"},
    }))
    assert ("node_modules/@s/p", "node_modules/x") in keys(g.edges)


def test_alias_uses_declared_name():
    g = parse_npm_lock(lock({
        "": {"dependencies": {"alias": "npm:real@1"}},
        "node_modules/alias": {"name": "real", "version": "1.0.0"},
    }))
    assert g.deps["node_modules/alias"].name == "real"


def test_workspace_member_is_first_party_and_its_deps_are_direct():
    g = parse_npm_lock(lock({
        "": {"workspaces": ["packages/*"]},
        "packages/app": {"version": "0.1.0", "dependencies": {"left": "1"}},
        "node_modules/app": {"resolved": "packages/app", "link": True},
        "node_modules/left": {"version": "1.0.0"},
    }))
    assert g.deps["packages/app"].workspace and g.deps["packages/app"].depth == 0
    assert g.deps["node_modules/left"].direct and g.deps["node_modules/left"].depth == 1
    assert "node_modules/app" not in g.deps  # the link is not a separate dependency


def test_unreachable_package_has_no_depth():
    g = parse_npm_lock(lock({
        "": {"dependencies": {"a": "1"}},
        "node_modules/a": {"version": "1.0.0"},
        "node_modules/orphan": {"version": "9.9.9"},
    }))
    assert g.deps["node_modules/orphan"].depth is None


def test_cycle_terminates():
    g = parse_npm_lock(lock({
        "": {"dependencies": {"a": "1"}},
        "node_modules/a": {"version": "1.0.0", "dependencies": {"b": "1"}},
        "node_modules/b": {"version": "1.0.0", "dependencies": {"a": "1"}},
    }))
    assert g.deps["node_modules/a"].depth == 1 and g.deps["node_modules/b"].depth == 2


def test_lockfile_v1_is_rejected():
    with pytest.raises(UnsupportedLockfile):
        parse_npm_lock(json.dumps({"lockfileVersion": 1, "dependencies": {}}))
