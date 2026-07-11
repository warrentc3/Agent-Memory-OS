#!/bin/sh
# Container entrypoint for the Agent Memory OS Web console.
set -eu

: "${AGENT_MEMORY_HOME:=/data}"
export AGENT_MEMORY_HOME
PORT="${AMOS_PORT:-8000}"

# Secure by default: a mapped port must not expose an open admin console. If no
# token is supplied via env and none is stored in the volume, generate one.
if [ -z "${AGENT_MEMORY_WEB_TOKEN:-}" ] && [ ! -f "${AGENT_MEMORY_HOME}/web_token" ]; then
  agent-memory token create >/dev/null 2>&1 || true
  echo "NOTE: no AGENT_MEMORY_WEB_TOKEN set — generated one in the data volume."
  echo "      Retrieve it with:  docker compose exec <service> agent-memory token show"
fi

# --strict-port: bind exactly this port (never drift) so it matches the
# published host:container mapping. 0.0.0.0 so it's reachable outside the container.
exec agent-memory-web --host 0.0.0.0 --port "${PORT}" --strict-port
