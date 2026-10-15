// Q6: across the whole fleet, which direct dependency drags the affected versions in, and how many artifacts it covers.
// Bumping the top row removes the most exposure. Params: $advisory, $at_ms
MATCH (adv:Advisory {id: $advisory})-[r:AFFECTS]->(pv:PackageVersion)<-[:IS]-(bad:LockedDep)<-[:LOCKS]-(a:Artifact)-[:LOCKS]->(top:LockedDep {direct: true})
WHERE adv.published_ms <= $at_ms AND coalesce(r.since_ms, 0) <= $at_ms
WITH a, top, bad, shortestPath((top)-[:REQUIRES*0..8]->(bad)) AS p
WHERE p IS NOT NULL
RETURN top.name AS direct, top.version AS version, count(DISTINCT a) AS artifacts, collect(DISTINCT a.id) AS in_artifacts
ORDER BY artifacts DESC, direct
