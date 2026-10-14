from plumbline.ingest.osv import normalise


RECORD = {
    "id": "MAL-2026-11561",
    "summary": "Malicious code in @cacheable/utils (npm)",
    "published": "2026-08-04T11:36:30Z",
    "affected": [{"package": {"name": "@cacheable/utils", "ecosystem": "npm"}, "versions": ["2.5.1"]}],
}


def test_scoped_package_purl_matches_lockfile_encoding():
    row = normalise(RECORD)
    assert row["purls"] == ["pkg:npm/%40cacheable/utils@2.5.1"]


def test_kind_and_timestamp():
    row = normalise(RECORD)
    assert row["kind"] == "MAL"
    assert row["published_ms"] == 1785843390000


def test_every_affected_version_becomes_a_purl():
    rec = {**RECORD, "affected": [{"package": {"name": "keyv", "ecosystem": "npm"}, "versions": ["6.0.0", "6.0.1"]}]}
    assert normalise(rec)["purls"] == ["pkg:npm/keyv@6.0.0", "pkg:npm/keyv@6.0.1"]
