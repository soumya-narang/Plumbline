// One row per advisory: {id, kind, package, summary, published, published_ms, affected: [{purl, name, version}]}
UNWIND $rows AS r
MERGE (adv:Advisory {id: r.id})
SET adv.kind = r.kind,
    adv.package = r.package,
    adv.summary = r.summary,
    adv.published = r.published,
    adv.published_ms = r.published_ms
WITH adv, r
UNWIND r.affected AS x
MERGE (pv:PackageVersion {purl: x.purl})
SET pv.name = x.name, pv.version = x.version, pv.ecosystem = 'npm'
MERGE (adv)-[:AFFECTS]->(pv)
