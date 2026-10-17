// Hand a fix to the remediation agents. One task per (advisory, artifact): asking again returns the same task.
// Params: $id, $advisory, $artifact, $fix, $note, $by, $now_ms
MATCH (adv:Advisory {id: $advisory}), (a:Artifact {id: $artifact})
MERGE (t:Task {id: $id})
ON CREATE SET t.status = 'open', t.advisory = $advisory, t.artifact = $artifact, t.fix = $fix, t.note = $note,
              t.created_by = $by, t.created_ms = $now_ms, t.claimed_by = '', t.claimed_ms = 0, t.resolution = '', t.done_ms = 0
MERGE (t)-[:ABOUT]->(adv)
MERGE (t)-[:FOR]->(a)
RETURN t.id AS id, t.status AS status, t.claimed_by AS claimed_by, t.created_ms = $now_ms AS created
