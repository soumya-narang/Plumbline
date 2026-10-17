#!/bin/sh
# Start the database, load the graph from the committed data, then serve the app.
set -eu

# The defaults (25 queued queries, a 1 s read timeout) are too tight for several visitors and agents at once.
redis-server --loadmodule /opt/falkordb/falkordb.so MAX_QUEUED_QUERIES 500 TIMEOUT_DEFAULT 5000 TIMEOUT_MAX 15000 RESULTSET_SIZE 10000 \
  --port "${FALKORDB_PORT:-6379}" --bind 127.0.0.1 --save "" --appendonly no &

for _ in $(seq 1 100); do
  redis-cli -p "${FALKORDB_PORT:-6379}" ping 2>/dev/null | grep -q PONG && break
  sleep 0.2
done

python -m plumbline load
exec python -m plumbline serve --host 0.0.0.0 --port "${PORT:-7860}"
