// When a tenant graph was created, by whom, and how big it is.
MATCH (a:Artifact)
OPTIONAL MATCH (a)-[:LOCKS]->(d:LockedDep)
RETURN a.id AS artifact, a.label AS label, a.created_ms AS created_ms, a.owner AS owner, count(d) AS packages
