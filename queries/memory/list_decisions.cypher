MATCH (d:Decision)-[:ABOUT]->(adv:Advisory), (d)-[:FOR]->(a:Artifact)
OPTIONAL MATCH (d)-[:ASSUMES]->(f:Fact)
RETURN d.id AS decision, d.verdict AS verdict, d.action AS action, d.status AS status, d.created_ms AS created_ms,
       d.approver AS approver, adv.id AS advisory, a.id AS artifact, collect(f.id) AS assumption_ids
ORDER BY created_ms, decision
