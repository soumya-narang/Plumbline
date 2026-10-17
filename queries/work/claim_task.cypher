// Take the oldest open task. This is one write query, and the graph runs write queries one at a time, so two agents
// can never claim the same task. Params: $agent, $now_ms
MATCH (t:Task {status: 'open'})
WITH t ORDER BY t.created_ms, t.id LIMIT 1
SET t.status = 'claimed', t.claimed_by = $agent, t.claimed_ms = $now_ms
RETURN t.id AS id, t.advisory AS advisory, t.artifact AS artifact, t.fix AS fix, t.note AS note
