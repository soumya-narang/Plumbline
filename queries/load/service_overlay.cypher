// DECLARED deployment overlay. One row per artifact: {artifact, service_id, name, tier, exposure_id, exposure}
UNWIND $rows AS r
MATCH (a:Artifact {id: r.artifact})
MERGE (s:Service {id: r.service_id})
SET s.name = r.name, s.tier = r.tier, s.declared = true
MERGE (e:Exposure {id: r.exposure_id})
SET e.kind = r.exposure, e.declared = true
MERGE (s)-[:RUNS]->(a)
MERGE (s)-[:EXPOSED_VIA]->(e)
