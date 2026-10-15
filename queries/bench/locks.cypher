// Does this artifact lock this exact package version? Params: $artifact, $name, $version
MATCH (:Artifact {id: $artifact})-[:LOCKS]->(:LockedDep {name: $name, version: $version})
RETURN count(*) > 0 AS locked
