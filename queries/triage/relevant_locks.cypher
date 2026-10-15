// Locked versions that matter for one advisory: the same package at any version, or any affected purl.
// Params: $package, $purls
MATCH (a:Artifact)-[:LOCKS]->(d:LockedDep)-[:IS]->(pv:PackageVersion)
WHERE pv.name = $package OR pv.purl IN $purls
RETURN a.id AS artifact, pv.purl AS purl, pv.name AS name, pv.version AS version,
       d.depth AS depth, d.dev AS dev
ORDER BY artifact, purl
