// Does this exposure rest on a version that a later revision added to the advisory (a scripted or visitor what-if)?
// Versions in the advisory as published have no since_ms. Params: $advisory, $purls
MATCH (:Advisory {id: $advisory})-[r:AFFECTS]->(pv:PackageVersion)
WHERE pv.purl IN $purls AND coalesce(r.since_ms, 0) > 0
RETURN count(r) AS revised
