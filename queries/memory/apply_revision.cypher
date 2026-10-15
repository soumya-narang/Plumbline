// A SCRIPTED advisory revision: the advisory later names additional versions as affected.
// The edge is stamped with since_ms and scripted = true so it is invisible before that time and is never
// mistaken for a real OSV record. Any fact asserting "this version is not affected" is superseded.
// Params: $advisory, $at_ms, $rows = [{purl, name, version}]
MATCH (adv:Advisory {id: $advisory})
UNWIND $rows AS r
MERGE (pv:PackageVersion {purl: r.purl})
  ON CREATE SET pv.name = r.name, pv.version = r.version, pv.ecosystem = 'npm'
MERGE (adv)-[e:AFFECTS]->(pv)
  ON CREATE SET e.since_ms = $at_ms, e.scripted = true
WITH adv, r
MATCH (f:Fact {id: 'not_affected:' + adv.id + ':' + r.purl})
SET f.superseded_ms = $at_ms
