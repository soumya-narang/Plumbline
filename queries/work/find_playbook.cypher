// What worked last time for this package. Params: $playbook
MATCH (p:Playbook {id: $playbook})
RETURN p.last_resolution AS resolution, p.uses AS uses
