// Artifacts whose lockfile was parsed, so a dependency graph can be drawn for them.
MATCH (a:Artifact {lock_state: 'present'})
RETURN a.id AS artifact
ORDER BY artifact
