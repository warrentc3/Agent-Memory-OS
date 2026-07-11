#!/bin/sh
# Container entrypoint for Agent Memory OS. The image is complete — web console,
# MCP server, and the CLI are all installed. The first argument selects the mode:
#
#   (default) | web   → the Web console         (docker run -p 8000:8000 …)
#   mcp               → the stdio MCP server     (docker run -i … mcp)
#   <anything else>   → passed through to the `agent-memory` CLI
#                       (e.g. docker run … check   /   docker run … stats)
set -eu

: "${AGENT_MEMORY_HOME:=/data}"
export AGENT_MEMORY_HOME

mode="${1:-web}"
case "$mode" in
  web)
    # Secure by default: a mapped port must not expose an open admin console.
    # If no token is supplied via env and none is stored in the volume, make one.
    if [ -z "${AGENT_MEMORY_WEB_TOKEN:-}" ] && [ ! -f "${AGENT_MEMORY_HOME}/web_token" ]; then
      agent-memory token create >/dev/null 2>&1 || true
      echo "NOTE: no AGENT_MEMORY_WEB_TOKEN set — generated one in the data volume."
      echo "      Retrieve it with:  docker compose exec <service> agent-memory token show"
    fi
    PORT="${AMOS_PORT:-8000}"
    # --strict-port: bind exactly this port (never drift) so it matches the
    # published host:container mapping. 0.0.0.0 so it's reachable outside.
    exec agent-memory-web --host 0.0.0.0 --port "${PORT}" --strict-port
    ;;
  mcp)
    # stdio MCP server (JSON-RPC over stdin/stdout): use `docker run -i`.
    exec python -m agent_memory_os.mcp_server
    ;;
  *)
    # Anything else runs the CLI, so `docker run … <cmd>` works like the tool.
    exec agent-memory "$@"
    ;;
esac
