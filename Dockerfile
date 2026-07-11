# Agent Memory OS — Web console container.
#
#   docker build -t agent-memory-os .
#   docker run -p 8000:8000 -v amos-data:/data agent-memory-os
#
# Semantic recall (turbovec) + MCP are opt-in to keep the default build fast
# and dependency-light:  docker build --build-arg EXTRAS=full  .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    AGENT_MEMORY_HOME=/data

WORKDIR /app
COPY . /app

# 'api' = FastAPI + uvicorn (the Web console). 'full' adds turbovec + MCP.
ARG EXTRAS=api
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

# No curl in slim — probe /health with the stdlib.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import os,urllib.request,sys; p=os.getenv('AMOS_PORT','8000'); sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+p+'/health',timeout=3).status==200 else 1)"]

ENTRYPOINT ["/app/docker/entrypoint.sh"]
