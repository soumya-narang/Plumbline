// One row per fleet entry: {id, kind, sha, committed_at, lockfile, lock_state, synthetic}
UNWIND $rows AS r
MERGE (a:Artifact {id: r.id})
SET a.kind = r.kind,
    a.sha = r.sha,
    a.committed_at = r.committed_at,
    a.lockfile = r.lockfile,
    a.lock_state = r.lock_state,
    a.synthetic = r.synthetic
