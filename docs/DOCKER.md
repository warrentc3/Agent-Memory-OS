# Running Agent Memory OS in Docker

The repo ships a `Dockerfile`, a single-instance `docker-compose.yml`, and a
two-node `docker-compose.mesh.yml`. Memories persist in a named volume mounted
at `/data` (the container's `AGENT_MEMORY_HOME`).

## Quick start (docker compose)

```bash
cp .env.example .env         # optional: set AGENT_MEMORY_WEB_TOKEN
docker compose up -d         # build + run; console at http://localhost:8000
docker compose logs -f amos  # watch startup
```

If you didn't set `AGENT_MEMORY_WEB_TOKEN`, the container generates one on first
run so the exposed port isn't an open admin console. Retrieve it with:

```bash
docker compose exec amos agent-memory token show
```

Stop / update / reset:

```bash
docker compose down                 # stop (keeps the data volume)
docker compose up -d --build        # rebuild after pulling new code
docker compose down -v              # stop AND delete memories (the volume)
```

## Plain docker

```bash
docker build -t agent-memory-os .
docker run -d --name amos -p 8000:8000 \
  -v amos-data:/data \
  -e AGENT_MEMORY_WEB_TOKEN=my-secret \
  agent-memory-os
```

Run any CLI command in the container:

```bash
docker exec amos agent-memory check
docker exec amos agent-memory node                 # show this node's identity
docker exec amos agent-memory retention
```

## Configuration (all optional, via environment)

| Variable | Default | Purpose |
|---|---|---|
| `AGENT_MEMORY_WEB_TOKEN` | auto-generated | Bearer token for the `/api/` routes. |
| `AGENT_MEMORY_NODE_NAME` | `host-<home>` label | Name shown to peers during sync. |
| `AMOS_PORT` | `8000` | Port inside the container (match your published mapping). |
| `AGENT_MEMORY_HOME` | `/data` | Data directory (the persistent volume). |

The image binds `0.0.0.0` and uses `--strict-port`, so it never drifts off the
published port. Semantic recall (turbovec) and MCP are omitted from the default
image to keep it small — build with them via:

```bash
docker build --build-arg EXTRAS=full -t agent-memory-os:full .
```

## Two nodes that sync (mesh)

`docker-compose.mesh.yml` runs `node-a` (`:8000`) and `node-b` (`:8001`), each
with its own volume and node name, sharing one token so they can authenticate
to each other:

```bash
echo "AGENT_MEMORY_WEB_TOKEN=$(openssl rand -hex 16)" > .env
docker compose -f docker-compose.mesh.yml up -d

# Register each as the other's peer (services resolve by name on the network):
TOK=$(grep AGENT_MEMORY_WEB_TOKEN .env | cut -d= -f2)
docker compose -f docker-compose.mesh.yml exec node-a \
  agent-memory peers add http://node-b:8000 --peer-token "$TOK" --policy full
docker compose -f docker-compose.mesh.yml exec node-b \
  agent-memory peers add http://node-a:8000 --peer-token "$TOK" --policy full

# Converge
docker compose -f docker-compose.mesh.yml exec node-a agent-memory sync auto
```

`--policy full` treats the two as your own trusted replicas (private memories
replicate). Use `--policy shared` between nodes you don't fully trust — private
memories then never leave. See the [User Guide](USER_GUIDE.md#6-federation--project-sync)
for the full trust model.

## Health

The image has a `HEALTHCHECK` hitting `/health`; `docker ps` shows `healthy`
once it's serving. `/health` is open (no token) precisely so orchestrators can
probe it.
