// Finish a task, but only for the agent that claimed it. Params: $id, $agent, $resolution, $now_ms
MATCH (t:Task {id: $id, status: 'claimed', claimed_by: $agent})
SET t.status = 'done', t.resolution = $resolution, t.done_ms = $now_ms
RETURN t.id AS id, t.advisory AS advisory, t.artifact AS artifact
