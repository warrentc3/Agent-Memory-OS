from __future__ import annotations

import argparse
import json
from .client import MemoryClient


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
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = MemoryClient(home=args.home)
    try:
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
    finally:
        client.close()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
