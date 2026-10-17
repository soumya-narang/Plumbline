// Mark the uploaded artifact with when it arrived, what the owner called it and who the owner is. Params: $now_ms, $label, $owner
MATCH (a:Artifact)
SET a.created_ms = $now_ms, a.label = $label, a.owner = $owner
