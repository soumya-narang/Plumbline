// Attach a receipt to a decision. Params: $decision, $hash, $payload (JSON text)
MATCH (d:Decision {id: $decision})
CREATE (r:Receipt {hash: $hash, payload: $payload})
CREATE (r)-[:PROVES]->(d)
