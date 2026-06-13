from __future__ import annotations

import argparse
import json
from .client import MemoryClient
from .golden_recall import evaluate_golden_queries, load_golden_query_cases
from .hermes_importer import import_hermes_memory_files
from .shadow_mode import summarize_shadow_log


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agent-memory", description="Local-first AI agent memory runtime")
    p.add_argument("--home", default=None, help="Memory home directory; defaults to AGENT_MEMORY_HOME or ~/.agent-memory")
    sub = p.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="Add a memory")
    add.add_argument("content")
    add.add_argument("--owner", default="default")
    add.add_argument("--scope", default="user")
    add.add_argument("--type", default="note")
    add.add_argument("--summary")
    add.add_argument("--tag", action="append", default=[])
    add.add_argument("--confidence", type=float, default=0.8)
    add.add_argument("--importance", type=float, default=0.5)

    search = sub.add_parser("search", help="Search memories")
    search.add_argument("query")
    search.add_argument("--owner")
    search.add_argument("--scope")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--json", action="store_true")

    pack = sub.add_parser("pack", help="Build a prompt-ready context pack")
    pack.add_argument("query")
    pack.add_argument("--owner")
    pack.add_argument("--scope")
    pack.add_argument("--limit", type=int, default=12)
    pack.add_argument("--max-tokens", type=int, default=1200)

    sub.add_parser("stats", help="Show database statistics")

    imp = sub.add_parser("import-hermes", help="Import Hermes MEMORY.md/USER.md into AgentMemoryOS")
    imp.add_argument("--profile", required=True, help="Hermes profile name / AgentMemoryOS owner")
    imp.add_argument("--profile-home", required=True, help="Hermes profile home containing memories/MEMORY.md and USER.md")
    imp.add_argument("--json", action="store_true", help="Emit JSON report")

    shadow = sub.add_parser("shadow-summary", help="Summarize shadow-mode JSONL evidence")
    shadow.add_argument("--log", required=True, help="Path to agent_memory_os_shadow.jsonl")
    shadow.add_argument("--last", type=int, default=None, help="Only summarize the last N records")
    shadow.add_argument("--json", action="store_true", help="Emit JSON evidence pack")

    golden = sub.add_parser("golden-recall", help="Run golden-query recall cases against the memory store")
    golden.add_argument("--cases", required=True, help="JSON/JSONL golden query case file")
    golden.add_argument("--limit", type=int, default=10, help="Default search limit for cases without limit")
    golden.add_argument("--recall-target", type=float, default=0.95, help="Required pass rate for GO")
    golden.add_argument("--json", action="store_true", help="Emit JSON evidence report")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "shadow-summary":
        summary = summarize_shadow_log(args.log, last_n=args.last)
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(
                f"records={summary['records']} activation_gate={summary['activation_gate']} "
                f"mean_top_k_hit_rate={summary['mean_top_k_hit_rate']} "
                f"p99_candidate_latency_ms={summary['p99_candidate_latency_ms']} "
                f"acl_leakage_count={summary['acl_leakage_count']} "
                f"production_injection_count={summary['production_injection_count']}"
            )
        return 0

    client = MemoryClient(home=args.home)
    try:
        if args.command == "golden-recall":
            cases = load_golden_query_cases(args.cases)
            report = evaluate_golden_queries(
                client,
                cases,
                default_limit=args.limit,
                recall_target=args.recall_target,
            )
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(
                    f"cases={report['cases']} passed={report['passed']} failed={report['failed']} "
                    f"golden_recall_rate={report['golden_recall_rate']} "
                    f"forbidden_hit_count={report['forbidden_hit_count']} "
                    f"activation_gate={report['activation_gate']}"
                )
            return 0
        if args.command == "add":
            rec = client.add(
                args.content, owner=args.owner, scope=args.scope, type=args.type,
                summary=args.summary, tags=args.tag, confidence=args.confidence, importance=args.importance,
            )
            print(rec.id)
            return 0
        if args.command == "search":
            results = client.search(args.query, owner=args.owner, scope=args.scope, limit=args.limit)
            if args.json:
                print(json.dumps([
                    {"id": r.record.id, "score": r.score, "content": r.record.content, "scope": r.record.scope, "type": r.record.type}
                    for r in results
                ], ensure_ascii=False, indent=2))
            else:
                for r in results:
                    print(f"{r.record.id}\t{r.score:.3f}\t{r.record.scope}/{r.record.type}\t{r.record.content}")
            return 0
        if args.command == "pack":
            print(client.context_pack(args.query, owner=args.owner, scope=args.scope, limit=args.limit, max_tokens=args.max_tokens), end="")
            return 0
        if args.command == "stats":
            print(json.dumps(client.stats(), ensure_ascii=False, indent=2))
            return 0
        if args.command == "import-hermes":
            report = import_hermes_memory_files(client, profile=args.profile, profile_home=args.profile_home)
            if args.json:
                print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
            else:
                print(
                    f"profile={report.profile} scanned={report.scanned} inserted={report.inserted} "
                    f"updated={report.updated} skipped={report.skipped}"
                )
            return 0
    finally:
        client.close()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
