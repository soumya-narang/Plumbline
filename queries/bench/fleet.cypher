// Which artifacts in the whole fleet lock this package version? Params: $name, $version
MATCH (a:Artifact)-[:LOCKS]->(:LockedDep {name: $name, version: $version})
RETURN DISTINCT a.id AS artifact
ORDER BY artifact
