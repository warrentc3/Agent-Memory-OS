"""v0.9.x validation harness — see docs/VALIDATION_PLAN.md.

Builds a deterministic synthetic multi-agent corpus, exercises the gate
matrix (G1 security, G2 functional, G3 performance), and writes a
professional report to docs/reports/ plus raw JSON to docs/reports/data/.

Usage:
    PYTHONPATH=src python scripts/validation_run.py [--quick] [--keep-home]
"""

from __future__ import annotations

import argparse
import json
import platform
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from agent_memory_os import MemoryClient, RecallProfile  # noqa: E402

RNG = random.Random(20260711)
WORDS = (
    "deploy pipeline staging rollback snapshot database index retention "
    "schedule review incident latency budget checklist canary token release "
    "monitor archive profile resonance cluster shard replica quota alert"
).split()
TEAMS = ["apollo", "zeus", "athena"]
AGENTS = {
    "cc-main": ("claude-code", ["apollo"]),
    "codex-1": ("codex", ["apollo", "zeus"]),
    "claw-1": ("openclaw", ["zeus"]),
    "hermes-neo": ("hermes", ["apollo", "athena"]),
    "hermes-mizuki": ("hermes", ["athena"]),
    "outsider": ("custom", []),
}


def pct(values, q):
    if not values:
        return 0.0
    values = sorted(values)
    index = min(len(values) - 1, max(0, int(round(q * (len(values) - 1)))))
    return values[index] * 1000  # ms


def timed(fn, iterations):
    samples = []
    for i in range(iterations):
        start = time.perf_counter()
        fn(i)
        samples.append(time.perf_counter() - start)
    return samples


def sentence(n=10):
    return " ".join(RNG.choice(WORDS) for _ in range(n))


def build_corpus(client, size, links):
    for agent_id, (kind, teams) in AGENTS.items():
        client.register_agent(agent_id, kind=kind, teams=teams)
        client.save_profile(RecallProfile(agent_id=agent_id, type_weights={"procedure": 1.2}))

    ids, per_sec = [], 0.0
    owners = [a for a in AGENTS if a != "outsider"]
    types = ["note", "fact", "procedure", "warning", "decision", "preference", "environment"]
    start = time.perf_counter()
    for i in range(size):
        owner = owners[i % len(owners)]
        roll = i % 10
        if roll < 2:
            visibility = []                                   # 20% private
        elif roll < 5:
            visibility = [f"team:{TEAMS[i % len(TEAMS)]}"]    # 30% team
        else:
            visibility = ["global"]                           # 50% global
        record = client.add(
            f"{sentence()} corpus item {i}.",
            owner=owner, type=types[i % len(types)], visibility=visibility,
            importance=0.3 + (i % 7) / 10, confidence=0.6 + (i % 4) / 10,
            pinned=(i % 97 == 0),
            source={"permanence": True, "weight": 10} if i % 131 == 0 else {},
        )
        ids.append(record.id)
    per_sec = size / (time.perf_counter() - start)

    for _ in range(links):
        a, b = RNG.sample(ids, 2)
        try:
            client.link(a, b, weight=0.3 + RNG.random() * 0.6)
        except ValueError:
            pass

    # recall probes: unique-token needles + no-overlap linked neighbors
    needles, neighbor_probes = [], []
    for n in range(25):
        needle = client.add(f"needle zxq{n:03d} unique marker memory.", owner="hermes-neo",
                            visibility=["global"])
        needles.append((f"zxq{n:03d}", needle.id))
        if n < 20:
            neighbor = client.add(f"companion wvb{n:03d} detail record.", owner="hermes-neo",
                                  visibility=["global"])
            client.link(needle.id, neighbor.id, weight=0.85)
            neighbor_probes.append((f"zxq{n:03d}", neighbor.id))
    return ids, per_sec, needles, neighbor_probes


def gate1_security(client, tmp):
    checks = []
    private = client.add("g1 secret sigil qqpp1.", owner="hermes-mizuki", visibility=[])
    teamed = client.add("g1 team sigil qqpp2.", owner="hermes-neo", visibility=["team:apollo"])

    def visible(query, requester, memory_id):
        return memory_id in {h.record.id for h in client.search(query, requester_agent_id=requester, limit=20)}

    checks.append(("private isolation (search)", not visible("secret sigil qqpp1", "hermes-neo", private.id), ""))
    checks.append(("private isolation (pack)", "qqpp1" not in client.context_pack("secret sigil qqpp1", requester_agent_id="hermes-neo"), ""))
    checks.append(("team member sees team memory", visible("team sigil qqpp2", "cc-main", teamed.id), "cc-main ∈ apollo"))
    checks.append(("non-member blocked", not visible("team sigil qqpp2", "hermes-mizuki", teamed.id), "mizuki ∉ apollo"))
    client.register_agent("cc-main", kind="claude-code", teams=[])
    checks.append(("membership edit immediate", not visible("team sigil qqpp2", "cc-main", teamed.id), "after leaving apollo"))
    client.register_agent("cc-main", kind="claude-code", teams=["apollo"])

    bridge_a = client.add("g1 bridge start rrss1.", owner="hermes-mizuki", visibility=["global"])
    bridge_p = client.add("g1 hidden middle.", owner="hermes-mizuki", visibility=[])
    bridge_c = client.add("g1 far public end.", owner="hermes-mizuki", visibility=["global"])
    client.link(bridge_a.id, bridge_p.id, weight=0.9)
    client.link(bridge_p.id, bridge_c.id, weight=0.9)
    hits = {h.record.id for h in client.search("bridge start rrss1", requester_agent_id="claw-1", limit=20)}
    checks.append(("resonance non-traversal", bridge_p.id not in hits and bridge_c.id not in hits, "private cannot bridge"))
    graph = client.graph_snapshot(requester_agent_id="claw-1")
    graph_ids = {node["id"] for node in graph["nodes"]}
    checks.append(("graph hides private", bridge_p.id not in graph_ids, ""))

    try:
        client.share_memory(private.id, actor="hermes-neo", to_agent="hermes-neo")
        checks.append(("non-owner share rejected", False, "PermissionError expected"))
    except PermissionError:
        checks.append(("non-owner share rejected", True, ""))
    client.share_memory(private.id, actor="hermes-mizuki", to_agent="hermes-neo")
    granted = visible("secret sigil qqpp1", "hermes-neo", private.id)
    client.revoke_share(private.id, actor="hermes-mizuki", to_agent="hermes-neo")
    revoked = not visible("secret sigil qqpp1", "hermes-neo", private.id)
    checks.append(("share grants / revoke removes", granted and revoked, "audited"))
    copy = client.share_memory(private.id, actor="hermes-mizuki", to_team="athena", deidentify=True)
    checks.append(("de-identified copy scrubbed", "hermes-mizuki" not in client.get(copy["shared_as"]).content, ""))

    before = client.get(private.id).confidence
    client.record_recall([private.id], helpful=False, requester_agent_id="claw-1")
    checks.append(("feedback gate", client.get(private.id).confidence == before, "invisible memory untouched"))

    bundle = tmp / "team-a.jsonl"
    client.export_bundle(bundle, team="apollo")
    lines = [json.loads(line) for line in bundle.read_text().splitlines()[1:]]
    leaked = [e for e in lines if e["kind"] == "memory" and "team:apollo" not in json.loads(e["visibility"])]
    checks.append(("team export boundary", not leaked, f"{len(lines)} rows"))
    return checks


def gate2_functional(client, tmp, needles, neighbor_probes, quick):
    checks = []
    pytest_pass = None
    if not quick:
        result = subprocess.run([sys.executable, "-m", "pytest", "-q", "--tb=no"],
                                cwd=REPO, capture_output=True, text=True)
        summary_lines = [line for line in result.stdout.strip().splitlines() if "passed" in line]
        tail = summary_lines[-1] if summary_lines else (result.stdout.strip().splitlines() or [""])[-1]
        pytest_pass = result.returncode == 0
        checks.append(("full test suite", pytest_pass, tail))

    hits = sum(
        1 for token, memory_id in needles
        if memory_id in {h.record.id for h in client.search(token, requester_agent_id="codex-1", limit=3)}
    )
    checks.append(("needle top-3 recall ≥95%", hits / len(needles) >= 0.95, f"{hits}/{len(needles)}"))
    surfaced = sum(
        1 for token, neighbor_id in neighbor_probes
        if neighbor_id in {h.record.id for h in client.search(token, requester_agent_id="codex-1", limit=10)}
    )
    checks.append(("linked-neighbor surfacing ≥90%", surfaced / len(neighbor_probes) >= 0.9,
                   f"{surfaced}/{len(neighbor_probes)} via resonance"))

    client.add("Never run retention on NAS homes.", type="warning", owner="hermes-neo",
               visibility=["global"], importance=0.95)
    ctx1 = client.orchestrate_context("deploy the staging pipeline", session_id="val-s1",
                                      requester_agent_id="hermes-neo", max_tokens=1200)
    ctx2 = client.orchestrate_context("deploy the staging pipeline", session_id="val-s1",
                                      requester_agent_id="hermes-neo", max_tokens=1200)
    repeat = set(ctx1.sections.get("task", {}).get("memory_ids", [])) & set(
        ctx2.sections.get("task", {}).get("memory_ids", []))
    checks.append(("orchestrator budget + buckets", ctx1.used_tokens <= 1200 and "warnings" in ctx1.sections, ""))
    checks.append(("session dedup", not repeat, f"{len(repeat)} repeats"))

    expired = [client.add(f"expired {i}.", visibility=["global"], expires_at="2020-01-01T00:00:00+00:00").id
               for i in range(5)]
    keeper = client.add("pinned keeper.", visibility=["global"], pinned=True)
    trusted = client.add("trusted fact.", type="fact", visibility=["global"])
    for _ in range(3):
        client.record_recall([trusted.id], helpful=True)
    retention_start = time.perf_counter()
    result = client.run_retention()
    retention_seconds = time.perf_counter() - retention_start
    restored = client.restore_archived(expired[0])
    checks.append(("retention archives expired set", result["archived_expired"] >= 5
                   and client.get(keeper.id) is not None and restored.expires_at is None,
                   f"{result}"))
    checks.append(("feedback tunes half-life", client.get(trusted.id).decay_half_life_days > 90.0,
                   f"{client.get(trusted.id).decay_half_life_days}d"))

    backup = tmp / "backup.db"
    import sqlite3
    src_conn = sqlite3.connect(client.home / "memories.db")
    dst_conn = sqlite3.connect(backup)
    src_conn.backup(dst_conn); dst_conn.close(); src_conn.close()
    restored_home = tmp / "restored"
    restored_home.mkdir()
    shutil.copy(backup, restored_home / "memories.db")
    twin = MemoryClient(home=restored_home)
    checks.append(("backup/restore parity", twin.stats()["total"] == client.stats()["total"],
                   f"{twin.stats()['total']} rows"))
    checks.append(("integrity + schema", client.integrity_check()["ok"],
                   f"schema v{client.integrity_check()['schema_version']}"))
    twin.close()

    fed_home = tmp / "fed"
    fed = MemoryClient(home=fed_home)
    bundle = tmp / "full.jsonl"
    export_start = time.perf_counter()
    client.export_bundle(bundle)
    export_seconds = time.perf_counter() - export_start
    import_start = time.perf_counter()
    fed.import_bundle(bundle)
    import_seconds = time.perf_counter() - import_start
    checks.append(("federation convergence", fed.stats()["total"] == client.stats()["total"]
                   and fed.stats()["links"] == client.stats()["links"],
                   f"{fed.stats()['total']} memories, {fed.stats()['links']} links"))
    fed.close()
    return checks, retention_seconds, export_seconds, import_seconds


def gate3_performance(client, iterations, timings):
    metrics = []
    queries = [f"{RNG.choice(WORDS)} {RNG.choice(WORDS)}" for _ in range(iterations)]
    search = timed(lambda i: client.search(queries[i], requester_agent_id="codex-1", limit=10), iterations)
    metrics.append(("search p50 (requester+teams+resonance)", pct(search, 0.50), 25, "ms"))
    metrics.append(("search p95", pct(search, 0.95), 80, "ms"))
    pack = timed(lambda i: client.context_pack(queries[i] + " x", requester_agent_id="codex-1"), iterations // 2)
    metrics.append(("context pack p95", pct(pack, 0.95), 100, "ms"))
    orches = timed(lambda i: client.orchestrate_context(queries[i], session_id=f"perf-{i%7}",
                                                        requester_agent_id="hermes-neo"), iterations // 2)
    metrics.append(("orchestrate p95", pct(orches, 0.95), 150, "ms"))
    graph = timed(lambda i: client.graph_snapshot(requester_agent_id="codex-1"), 10)
    metrics.append(("graph snapshot avg", statistics.mean(graph) * 1000, 250, "ms"))
    dash = timed(lambda i: client.dashboard_stats(), 10)
    metrics.append(("dashboard avg", statistics.mean(dash) * 1000, 250, "ms"))
    metrics.append(("retention full pass", timings["retention"] * 1000, 5000, "ms"))
    consolidate_start = time.perf_counter()
    client.consolidate()
    metrics.append(("consolidation", (time.perf_counter() - consolidate_start) * 1000, 10000, "ms"))
    metrics.append(("bundle export", timings["export"] * 1000, 10000, "ms"))
    metrics.append(("bundle import", timings["import"] * 1000, 10000, "ms"))

    semantic = None
    try:
        import turbovec  # noqa: F401
        from agent_memory_os.embedding import AutoSemanticIndex

        index = AutoSemanticIndex(client.store)
        build_start = time.perf_counter()
        index.candidates("warm up the index", limit=5)
        build_seconds = time.perf_counter() - build_start
        query_samples = timed(lambda i: index.candidates(queries[i % len(queries)], limit=10), 50)
        metrics.append(("semantic index build", build_seconds * 1000, 30000, "ms"))
        metrics.append(("semantic query p95", pct(query_samples, 0.95), 50, "ms"))
        semantic = True
    except ImportError:
        semantic = False
    return metrics, semantic


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="CI-sized smoke run")
    parser.add_argument("--keep-home", action="store_true")
    args = parser.parse_args()

    size, links, iterations = (400, 150, 30) if args.quick else (5000, 2000, 200)
    version = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["version"]
    stamp = datetime.now(timezone.utc)
    tmp = Path(tempfile.mkdtemp(prefix="amos-validation-"))
    home = tmp / "home"

    client = MemoryClient(home=home, semantic=None)
    ids, add_per_sec, needles, neighbor_probes = build_corpus(client, size, links)
    g1 = gate1_security(client, tmp)
    g2, retention_s, export_s, import_s = gate2_functional(client, tmp, needles, neighbor_probes, args.quick)
    g3, semantic_available = gate3_performance(
        client, iterations, {"retention": retention_s, "export": export_s, "import": import_s})
    g3.insert(0, ("write throughput", add_per_sec, 200, "memories/s"))
    stats = client.stats()
    client.close()
    if not args.keep_home:
        shutil.rmtree(tmp, ignore_errors=True)

    g1_ok = all(ok for _, ok, _ in g1)
    g2_ok = all(ok for _, ok, _ in g2)
    def g3_status(name, actual, target):
        if name == "write throughput":
            return "PASS" if actual >= target else ("FAIL" if actual < target / 3 else "WARN")
        return "PASS" if actual <= target else ("FAIL" if actual > target * 3 else "WARN")
    g3_rows = [(name, actual, target, unit, g3_status(name, actual, target)) for name, actual, target, unit in g3]
    g3_fail = any(status == "FAIL" for *_, status in g3_rows)
    g3_warn = any(status == "WARN" for *_, status in g3_rows)
    verdict = "FAIL" if (not g1_ok or not g2_ok or g3_fail) else ("CONDITIONAL" if g3_warn else "PASS")

    mode = "quick" if args.quick else "full"
    date = stamp.strftime("%Y%m%d")
    reports = REPO / "docs" / "reports"
    (reports / "data").mkdir(parents=True, exist_ok=True)
    payload = {
        "version": version, "mode": mode, "generated_at": stamp.isoformat(timespec="seconds"),
        "environment": {"platform": platform.platform(), "python": platform.python_version(),
                        "machine": platform.machine(), "semantic_backend": semantic_available},
        "corpus": {"memories": stats["total"], "links": stats["links"], "agents": len(AGENTS),
                   "teams": len(TEAMS)},
        "g1": [{"check": c, "ok": ok, "detail": d} for c, ok, d in g1],
        "g2": [{"check": c, "ok": ok, "detail": d} for c, ok, d in g2],
        "g3": [{"metric": n, "actual": round(a, 2), "target": t, "unit": u, "status": s}
                for n, a, t, u, s in g3_rows],
        "verdict": verdict,
    }
    json_path = reports / "data" / f"{date}-v{version}-{mode}.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    def mark(ok): return "✅ PASS" if ok else "❌ FAIL"
    lines = [
        f"# Validation Report — Agent Memory OS v{version} ({mode} run)",
        "",
        f"Generated {stamp.strftime('%Y-%m-%d %H:%M UTC')} by `scripts/validation_run.py` "
        f"per [VALIDATION_PLAN.md](../VALIDATION_PLAN.md). Raw data: "
        f"[`data/{json_path.name}`](data/{json_path.name}).",
        "",
        f"## Verdict: **{verdict}**",
        "",
        f"- G1 Security & ACL: **{'PASS' if g1_ok else 'FAIL'}** ({sum(ok for _, ok, _ in g1)}/{len(g1)})",
        f"- G2 Functional: **{'PASS' if g2_ok else 'FAIL'}** ({sum(ok for _, ok, _ in g2)}/{len(g2)})",
        f"- G3 Performance: **{'FAIL' if g3_fail else ('WARN' if g3_warn else 'PASS')}**",
        "",
        "## Environment",
        "",
        f"| Platform | Python | Machine | Semantic backend |",
        f"|---|---|---|---|",
        f"| {platform.platform()} | {platform.python_version()} | {platform.machine()} | "
        f"{'turbovec available' if semantic_available else 'not installed (lexical+resonance only)'} |",
        "",
        "## Corpus",
        "",
        f"{stats['total']:,} memories · {stats['links']:,} links · {len(AGENTS)} agents "
        f"across {len(TEAMS)} teams · visibility mix ≈ 20% private / 30% team / 50% global · "
        "deterministic seed 20260711.",
        "",
        "## G1 — Security & ACL (hard gates)",
        "",
        "| Check | Result | Detail |",
        "|---|---|---|",
        *[f"| {c} | {mark(ok)} | {d} |" for c, ok, d in g1],
        "",
        "## G2 — Functional correctness",
        "",
        "| Check | Result | Detail |",
        "|---|---|---|",
        *[f"| {c} | {mark(ok)} | {d} |" for c, ok, d in g2],
        "",
        "## G3 — Performance",
        "",
        "| Metric | Actual | Target | Status |",
        "|---|---|---|---|",
        *[f"| {n} | {a:,.1f} {u} | {'≥' if u.endswith('/s') else '≤'} {t:,} {u} | {s} |"
          for n, a, t, u, s in g3_rows],
        "",
        "## Notes",
        "",
        "- Performance figures are single-host, local-disk, synthetic-corpus "
        "numbers; re-run on production-representative hardware before "
        "adoption decisions (see plan §Verdict rules).",
        "- G1 checks are hard gates: any failure fails the run regardless of "
        "other results.",
        "",
    ]
    report_path = reports / f"{date}-v{version}-validation-report.md"
    report_path.write_text("\n".join(lines))
    print(f"verdict: {verdict}")
    print(f"report:  {report_path.relative_to(REPO)}")
    print(f"data:    {json_path.relative_to(REPO)}")
    return 0 if verdict != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
