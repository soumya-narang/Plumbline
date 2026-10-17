// Procedural memory: remember how a package's incident was resolved, so the next hand-off can suggest it.
// Params: $playbook, $package, $task, $resolution, $now_ms
MERGE (p:Playbook {id: $playbook})
ON CREATE SET p.package = $package, p.uses = 0
SET p.uses = p.uses + 1, p.last_resolution = $resolution, p.last_ms = $now_ms
WITH p
MATCH (t:Task {id: $task})
MERGE (t)-[:USED]->(p)
RETURN p.uses AS uses
