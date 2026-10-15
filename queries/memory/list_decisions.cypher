MATCH (d:Decision)-[:ABOUT]->(adv:Advisory), (d)-[:FOR]->(a:Artifact)
OPTIONAL MATCH (d)-[:ASSUMES]->(f:Fact)
RETURN d.id AS decision, d.verdict AS verdict, d.action AS action, d.status AS status, d.created_ms AS created_ms,
       adv.id AS advisory, a.id AS artifact, count(f) AS assumptions
ORDER BY created_ms, decision
