// One row per advisory: {id, kind, package, summary, published, published_ms, purls[]}
UNWIND $rows AS r
MERGE (adv:Advisory {id: r.id})
SET adv.kind = r.kind,
    adv.package = r.package,
    adv.summary = r.summary,
    adv.published = r.published,
    adv.published_ms = r.published_ms
WITH adv, r
UNWIND r.purls AS purl
MERGE (pv:PackageVersion {purl: purl})
MERGE (adv)-[:AFFECTS]->(pv)
