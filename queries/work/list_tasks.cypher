// The shared work queue, oldest first. Params: $status (empty string for every status)
MATCH (t:Task)
WHERE $status = '' OR t.status = $status
RETURN t.id AS id, t.status AS status, t.advisory AS advisory, t.artifact AS artifact, t.fix AS fix, t.note AS note,
       t.created_by AS created_by, t.claimed_by AS claimed_by, t.resolution AS resolution,
       t.created_ms AS created_ms, t.claimed_ms AS claimed_ms, t.done_ms AS done_ms, t.hypothetical AS hypothetical
ORDER BY t.created_ms, t.id
