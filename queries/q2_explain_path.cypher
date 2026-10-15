// Q2: shortest dependency chain from a direct dependency to the affected locked package.
// shortestPath is only valid in WITH/RETURN on this engine; *0..8 lets a direct dependency return length 0.
// Params: $artifact (Artifact.id), $purl (PackageVersion.purl)
MATCH (a:Artifact {id: $artifact})-[:LOCKS]->(bad:LockedDep)-[:IS]->(:PackageVersion {purl: $purl}),
      (a)-[:LOCKS]->(top:LockedDep {direct: true})
WITH top, bad, shortestPath((top)-[:REQUIRES*0..8]->(bad)) AS p
WHERE p IS NOT NULL
RETURN [n IN nodes(p) | n.name + '@' + n.version] AS chain, length(p) AS hops
ORDER BY hops
LIMIT 1
