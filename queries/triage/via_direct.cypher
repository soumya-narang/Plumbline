// The direct dependencies of one artifact that pull an affected version in. Params: $artifact, $purl
MATCH (a:Artifact {id: $artifact})-[:LOCKS]->(bad:LockedDep)-[:IS]->(:PackageVersion {purl: $purl}),
      (a)-[:LOCKS]->(top:LockedDep {direct: true})
WITH top, bad, shortestPath((top)-[:REQUIRES*0..8]->(bad)) AS p
WHERE p IS NOT NULL
RETURN DISTINCT top.name AS name, top.version AS version
ORDER BY name
