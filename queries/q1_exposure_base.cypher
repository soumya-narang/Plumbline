// Q1: every (advisory, service) pair where a service's artifact locks an affected package version.
MATCH (adv:Advisory)-[:AFFECTS]->(pv:PackageVersion)<-[:IS]-(d:LockedDep)<-[:LOCKS]-(a:Artifact)<-[:RUNS]-(s:Service)
RETURN adv.id AS advisory, s.name AS service, a.id AS artifact, pv.purl AS purl, d.depth AS depth
ORDER BY advisory, service
