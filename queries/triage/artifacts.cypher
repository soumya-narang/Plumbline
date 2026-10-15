// Every artifact with its declared service, tier and exposure.
MATCH (a:Artifact)
OPTIONAL MATCH (s:Service)-[:RUNS]->(a)
OPTIONAL MATCH (s)-[:EXPOSED_VIA]->(e:Exposure)
RETURN a.id AS artifact, a.kind AS kind, a.lock_state AS lock_state, a.lock_sha256 AS lock_sha256,
       s.name AS service, s.tier AS tier, e.kind AS exposure
ORDER BY artifact
