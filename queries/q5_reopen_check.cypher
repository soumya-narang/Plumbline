// Q5: which accepted decisions rest on an assumption that has since been superseded?
// Truth maintenance in one query: a fact is superseded when a later event contradicts it.
// Params: $at_ms
MATCH (d:Decision {status: 'accepted'})-[:ASSUMES]->(f:Fact)
WHERE f.superseded_ms IS NOT NULL AND f.superseded_ms <= $at_ms
MATCH (d)-[:ABOUT]->(adv:Advisory), (d)-[:FOR]->(a:Artifact)
RETURN d.id AS decision, d.verdict AS verdict, adv.id AS advisory, a.id AS artifact,
       collect(f.id) AS broken, max(f.superseded_ms) AS broken_ms
ORDER BY decision
