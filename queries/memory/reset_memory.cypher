// Remove everything the replay writes, restoring the loaded graph. Scripted edges are removed separately.
MATCH (n) WHERE n:Decision OR n:Fact OR n:Receipt
DETACH DELETE n
