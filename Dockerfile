# One container: FalkorDB (copied from the official image) plus the Plumbline API and UI.
# Runs as an unprivileged user and listens on $PORT (default 7860).

FROM falkordb/falkordb:latest AS database

FROM python:3.13-slim-trixie
RUN apt-get update \
 && apt-get install -y --no-install-recommends libstdc++6 libgomp1 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=database /usr/local/bin/redis-server /usr/local/bin/redis-server
COPY --from=database /usr/local/bin/redis-cli /usr/local/bin/redis-cli
COPY --from=database /var/lib/falkordb/bin/falkordb.so /opt/falkordb/falkordb.so

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e .

COPY queries ./queries
COPY data ./data
COPY web ./web
COPY deploy/entrypoint.sh /entrypoint.sh

RUN useradd --create-home --uid 1000 app && chmod +x /entrypoint.sh
USER app
ENV FALKORDB_HOST=127.0.0.1 FALKORDB_PORT=6379 PORT=7860
EXPOSE 7860
ENTRYPOINT ["/entrypoint.sh"]
