"""Performance benchmark for AgentMemoryOS at scale.

Seeds N memories across agents/teams/projects, then times the hot paths:
add, search (with ACL resolution), context-pack orchestration, usage_summary,
and a federated export/import round-trip. Prints a small report.

Usage: python scripts/perf_bench.py [N]   (default N=10000)
"""

from __future__ import annotations

import statistics
import sys
import tempfile
import time

from agent_memory_os import MemoryClient


def _time(fn, *, repeat=1):
    samples = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000)
    return samples


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000
    home = tempfile.mkdtemp()
    c = MemoryClient(home=home)

    agents = [f"agent-{i}" for i in range(20)]
    for a in agents:
        c.store.register_agent(a)
    for t in range(5):
        c.store.create_team(f"team-{t}")
        for a in agents[t * 4:(t + 1) * 4]:
            c.store.add_team_member(f"team-{t}", a)
        c.store.create_project(f"proj-{t}", f"team-{t}")
        for a in agents[t * 4:(t + 1) * 4][:2]:
            c.store.add_project_member(f"proj-{t}", a)

    words = ("retrieval pipeline memory federation sync agent team project token "
             "resonance decay archive index vector semantic recall context").split()
    print(f"seeding {n} memories…")
    t0 = time.perf_counter()
    for i in range(n):
        owner = agents[i % len(agents)]
        vis = ["global"] if i % 3 == 0 else ([f"team:team-{i % 5}"] if i % 3 == 1
                                             else [f"project:proj-{i % 5}"])
        content = " ".join(words[(i + k) % len(words)] for k in range(12)) + f" item {i}"
        c.add(content, owner=owner, visibility=vis)
    seed_s = time.perf_counter() - t0
    add_ms = seed_s / n * 1000

    def search():
        c.search("memory federation sync", requester_agent_id="agent-1", limit=20)

    def pack():
        c.orchestrate_context("retrieval pipeline token", requester_agent_id="agent-1",
                              max_tokens=2000)

    def usage():
        c.usage_summary()

    def scan():
        c.maintenance_scan()

    search_ms = _time(search, repeat=15)
    pack_ms = _time(pack, repeat=10)
    usage_ms = _time(usage, repeat=5)
    scan_ms = _time(scan, repeat=5)

    # federated round-trip
    dst = MemoryClient(home=tempfile.mkdtemp())
    exp = tempfile.mktemp(suffix=".jsonl")

    def export():
        c.export_bundle(exp)

    def imp():
        dst.import_bundle(exp, org_scope="full")

    export_ms = _time(export)[0]
    import_ms = _time(imp)[0]

    def line(label, samples):
        return (f"{label:28s} p50={statistics.median(samples):8.2f}ms  "
                f"max={max(samples):8.2f}ms  (n={len(samples)})")

    print("\n=== AgentMemoryOS performance ===")
    print(f"memories: {n}   db: {home}")
    print(f"{'add (per memory)':28s} avg={add_ms:8.3f}ms  ({seed_s:.1f}s total)")
    print(line("search (ACL-gated)", search_ms))
    print(line("orchestrate_context", pack_ms))
    print(line("usage_summary (4 cards)", usage_ms))
    print(line("maintenance_scan", scan_ms))
    print(f"{'export_bundle':28s} {export_ms:8.2f}ms")
    print(f"{'import_bundle':28s} {import_ms:8.2f}ms")
    total = c.stats()["total"]
    print(f"\nintegrity: {c.integrity_check()['ok']}   total in store: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
