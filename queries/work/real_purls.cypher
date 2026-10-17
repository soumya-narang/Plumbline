// Which of these versions does the advisory name as published (not added later by a revision, scripted or a what-if)?
// Params: $advisory, $purls
MATCH (:Advisory {id: $advisory})-[r:AFFECTS]->(pv:PackageVersion)
WHERE pv.purl IN $purls AND coalesce(r.since_ms, 0) = 0
RETURN pv.purl AS purl
ORDER BY purl
