#!/bin/sh
# Start the database, load the graph from the committed data, then serve the app.
set -eu

redis-server --loadmodule /opt/falkordb/falkordb.so MAX_QUEUED_QUERIES 25 TIMEOUT 1000 RESULTSET_SIZE 10000 \
  --port "${FALKORDB_PORT:-6379}" --bind 127.0.0.1 --save "" --appendonly no &

for _ in $(seq 1 100); do
  redis-cli -p "${FALKORDB_PORT:-6379}" ping 2>/dev/null | grep -q PONG && break
  sleep 0.2
done

python -m plumbline load
exec python -m plumbline serve --host 0.0.0.0 --port "${PORT:-7860}"
