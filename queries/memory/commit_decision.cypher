// Write one approved decision and the facts it assumes. Params: $id, $advisory, $artifact, $verdict, $reason,
// $action, $at_ms, $approver, $policy_version, $assumptions = [{id, kind, key}]
MATCH (adv:Advisory {id: $advisory}), (a:Artifact {id: $artifact})
CREATE (d:Decision {id: $id, verdict: $verdict, reason: $reason, action: $action, status: 'accepted',
                    created_ms: $at_ms, approver: $approver, policy_version: $policy_version})
CREATE (d)-[:ABOUT]->(adv)
CREATE (d)-[:FOR]->(a)
WITH d
UNWIND $assumptions AS x
MERGE (f:Fact {id: x.id})
  ON CREATE SET f.kind = x.kind, f.key = x.key, f.created_ms = $at_ms
CREATE (d)-[:ASSUMES]->(f)
