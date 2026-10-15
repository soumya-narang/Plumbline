// Third-party dependencies. One row per dep: {artifact, id, key, name, version, purl, direct, dev, optional, depth}
UNWIND $rows AS r
MATCH (a:Artifact {id: r.artifact})
MERGE (pv:PackageVersion {purl: r.purl})
  ON CREATE SET pv.name = r.name, pv.version = r.version, pv.ecosystem = 'npm'
CREATE (d:LockedDep {id: r.id, key: r.key, name: r.name, version: r.version, direct: r.direct, dev: r.dev, optional: r.optional, depth: r.depth})
CREATE (a)-[:LOCKS]->(d)
CREATE (d)-[:IS]->(pv)
