// An advisory as known at $at_ms: published by then, with only the affected versions added by then.
// Params: $advisory, $at_ms
MATCH (adv:Advisory {id: $advisory})
WHERE adv.published_ms <= $at_ms
OPTIONAL MATCH (adv)-[r:AFFECTS]->(pv:PackageVersion)
WHERE coalesce(r.since_ms, 0) <= $at_ms
RETURN adv.id AS advisory, adv.package AS package, adv.published_ms AS published_ms, collect(pv.purl) AS purls
