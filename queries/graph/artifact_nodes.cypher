// Every third-party install in one artifact's lockfile. Params: $artifact
MATCH (:Artifact {id: $artifact})-[:LOCKS]->(d:LockedDep)
WHERE d.workspace IS NULL
RETURN d.key AS key, d.name AS name, d.version AS version, d.depth AS depth, d.direct AS direct
ORDER BY d.depth, d.key
