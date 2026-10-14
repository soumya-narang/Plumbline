// Resolved dependency edges within one artifact. One row per edge: {from, to}
UNWIND $rows AS r
MATCH (x:LockedDep {id: r.from}), (y:LockedDep {id: r.to})
CREATE (x)-[:REQUIRES]->(y)
