// Which direct dependencies of an artifact pull this package version in, however deep? Params: $artifact, $name, $version
MATCH (a:Artifact {id: $artifact})-[:LOCKS]->(target:LockedDep {name: $name, version: $version}),
      (a)-[:LOCKS]->(top:LockedDep {direct: true})
WITH top, target, shortestPath((top)-[:REQUIRES*0..12]->(target)) AS p
WHERE p IS NOT NULL
RETURN DISTINCT top.name AS name
ORDER BY name
