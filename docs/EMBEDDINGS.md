# Semantic recall: embeddings & scale

Semantic recall lets a query match a memory by *meaning*, not just keywords.
AgentMemoryOS ships a zero-dependency default and lets you plug in a real
embedding model when you want stronger semantics.

## The default (no setup)

```python
client = MemoryClient(home="~/.agent-memory", semantic="auto")
```

`semantic="auto"` wires a self-syncing **turbovec** index over a built-in
**deterministic hashing embedder** — no model downloads, no network. It gives
typo- and morphology-tolerant *lexical* vectors and rebuilds itself whenever the
memories table changes. It is a soft ranking signal on top of the SQLite/FTS5
truth store, so it is safe and always available; it just doesn't capture deep
semantics (paraphrase, synonyms across languages).

## Plugging in a real embedding model

Any function `str -> list[float]` works. Pick a model, then build a provider
over your current memories and append it to the store's candidate providers:

```python
from agent_memory_os import MemoryClient
from agent_memory_os.providers.turbovec import TurbovecSemanticCandidateProvider

# --- choose ONE embedder (both fully local) ---
# fastembed (ONNX, small, no torch):   pip install fastembed
from fastembed import TextEmbedding
_model = TextEmbedding("BAAI/bge-small-en-v1.5")   # 384-dim, ~130MB, CPU-fine
def embed(text: str) -> list[float]:
    return next(_model.embed([text])).tolist()

# sentence-transformers:               pip install sentence-transformers
#   from sentence_transformers import SentenceTransformer
#   _model = SentenceTransformer("all-MiniLM-L6-v2")   # 384-dim
#   def embed(text): return _model.encode(text, normalize_embeddings=True).tolist()

client = MemoryClient(home="~/.agent-memory")

def install_semantic_index(client) -> None:
    records = client.list_recent(limit=1_000_000)          # admin view = every memory
    if not records:
        return
    external_id_by_memory_id = {r.id: i for i, r in enumerate(records)}
    vectors = [embed(r.content) for r in records]           # row i ↔ records[i]
    provider = TurbovecSemanticCandidateProvider.from_vectors(
        vectors=vectors,
        external_id_by_memory_id=external_id_by_memory_id,
        embed_query=embed,
    )
    client.store.candidate_providers.append(provider)

install_semantic_index(client)
```

This builds a **point-in-time** index: it covers the memories that existed when
you called it. After a bulk import (or periodically), rebuild it by constructing
a fresh provider the same way. If you want a self-resyncing index like the
`semantic="auto"` default (which rebuilds on every write), subclass
`AutoSemanticIndex` (`agent_memory_os/providers/turbovec.py`) and override its
embedder — it re-embeds automatically when the memories table changes.

**Invariant unchanged:** the provider only returns candidate `memory_id`s; every
candidate still rejoins SQLite and passes the ACL + expiry hard gates before its
content is used. Swapping the embedder never weakens access control — it only
changes which candidates surface for ranking. `agent-memory doctor` confirms the
turbovec backend is importable.

**Stability note:** if you pin an external model, keep it fixed — changing the
model changes the vector space and forces a full re-embed. The hashing embedder's
vectors are not a compatibility surface (see `COMPATIBILITY.md`).

## Scale guidance

The store is one SQLite file with FTS5 + a rebuildable vector index. Rough,
single-node expectations (verified at 10k; extrapolated above that):

| Memories | Behaviour | What to do |
|---|---|---|
| **≤ 10k** | Everything is instant (add ~0.2 ms, search < 1 ms, context-pack ~8 ms). | Nothing — defaults are fine. |
| **10k – 100k** | Still comfortably interactive on a laptop. FTS5 stays fast; the in-memory vector index grows linearly in RAM. | Enable retention so idle/expired memories archive out of the hot set (`agent-memory retention`). Run `vacuum` occasionally. |
| **100k – 1M** | Feasible, but the in-memory vector index and full-table scans start to cost RAM/latency. | Lean on **teams/projects** to keep working sets small (scope queries), archive aggressively, and consider an external embedding + vector store behind the same provider interface if you need ANN at that size. |
| **> 1M** | Beyond the local-first sweet spot. | Split by team/project across nodes and let **federation** converge them, rather than one giant store. |

Because SQLite is the source of truth and indexes are disposable, you can always
`rebuild_indexes()` after bulk imports or archival without risking data. Keep the
database on a **local disk** — network filesystems (NFS/SMB) break SQLite locking.
