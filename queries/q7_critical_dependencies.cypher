// Q7: the packages an artifact leans on most, ranked by PageRank over the REQUIRES graph.
// A compromise of a high-ranked package reaches the most of the tree. Params: $prefix (artifact id plus ::), $limit
CALL algo.pageRank('LockedDep', 'REQUIRES') YIELD node, score
WHERE node.id STARTS WITH $prefix AND node.workspace IS NULL
RETURN node.name AS name, node.version AS version, score
ORDER BY score DESC
LIMIT $limit
