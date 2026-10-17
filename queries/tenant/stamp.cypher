// Mark the uploaded artifact with when it arrived and what the owner called it. Params: $now_ms, $label
MATCH (a:Artifact)
SET a.created_ms = $now_ms, a.label = $label
