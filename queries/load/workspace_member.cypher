// First-party workspace members have no PackageVersion. One row per member: {artifact, id, key, name, depth}
UNWIND $rows AS r
MATCH (a:Artifact {id: r.artifact})
CREATE (d:LockedDep {id: r.id, key: r.key, workspace: true, direct: false, dev: false, optional: false, depth: 0})
CREATE (a)-[:LOCKS]->(d)
