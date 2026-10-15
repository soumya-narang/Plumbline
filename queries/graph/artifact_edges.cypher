// The resolved REQUIRES edges inside one artifact's lockfile. Params: $artifact
MATCH (:Artifact {id: $artifact})-[:LOCKS]->(x:LockedDep)-[:REQUIRES]->(y:LockedDep)
WHERE x.workspace IS NULL AND y.workspace IS NULL
RETURN x.key AS source, y.key AS target
