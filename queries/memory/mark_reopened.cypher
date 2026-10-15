// Params: $id, $at_ms
MATCH (d:Decision {id: $id})
SET d.status = 'reopened', d.reopened_ms = $at_ms
