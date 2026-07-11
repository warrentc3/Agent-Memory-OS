# Agent Memory OS — complete container (Web console + MCP server + CLI).
#
#   docker build -t agent-memory-os .
#   docker run -p 8000:8000 -v amos-data:/data agent-memory-os        # web console (default)
#   docker run -i --rm agent-memory-os mcp                             # stdio MCP server
#   docker run --rm -v amos-data:/data agent-memory-os check          # any CLI command
#
# The image installs the 'full' extra (turbovec + MCP) so every surface works
# out of the box. For a lean, web-only build:  docker build --build-arg EXTRAS=api .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    AGENT_MEMORY_HOME=/data

WORKDIR /app
COPY . /app

# 'full' = Web console + MCP server + turbovec (complete). 'api' = web only (lean).
ARG EXTRAS=full
RUN pip install ".[${EXTRAS}]"

# Run unprivileged; /data holds memories.db, the token, and instance.toml and
# is the mount point for persistence.
RUN useradd --create-home --uid 10001 amos \
 && mkdir -p /data \
 && chown -R amos:amos /data /app \
 && chmod +x /app/docker/entrypoint.sh
USER amos

VOLUME ["/data"]
EXPOSE 8000

# No curl in slim — probe /healthz (integrity-aware readiness) with the stdlib.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import os,urllib.request,sys; p=os.getenv('AMOS_PORT','8000'); sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+p+'/healthz',timeout=3).status==200 else 1)"]

ENTRYPOINT ["/app/docker/entrypoint.sh"]
