// How many tasks are waiting or in progress; used to keep the queue bounded.
MATCH (t:Task) WHERE t.status <> 'done'
RETURN count(t) AS open
