// How big the uploaded graph is: installs and the resolved requirement edges between them.
MATCH (:Artifact)-[:LOCKS]->(d:LockedDep)
WHERE d.workspace IS NULL
OPTIONAL MATCH (d)-[r:REQUIRES]->(:LockedDep)
RETURN count(DISTINCT d) AS installs, count(r) AS requirements
