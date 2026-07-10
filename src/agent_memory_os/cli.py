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

    token = sub.add_parser("token", help="Manage the Web UI API token")
    token.add_argument("action", choices=["create", "show", "rotate", "disable"])

    doctor = sub.add_parser("doctor", help="Check optional dependencies and setup health")
    doctor.add_argument("--install", action="store_true", help="pip-install any missing optional extras")

    backup = sub.add_parser("backup", help="Back up the memory database to a file")
    backup.add_argument("dest", help="Destination .db file path")

    restore = sub.add_parser("restore", help="Restore the memory database from a backup file")
    restore.add_argument("src", help="Backup .db file to restore from")
    restore.add_argument("--force", action="store_true", help="Overwrite an existing database")

    sub.add_parser("check", help="Run database integrity and invariant checks")

    service = sub.add_parser(
        "service", help="Install the Web console as a login service (launchd/systemd/Task Scheduler)"
    )
    service.add_argument("action", choices=["install", "uninstall", "start", "stop", "status"])
    service.add_argument("--host", default="127.0.0.1")
    service.add_argument("--port", type=int, default=8000)
    service.add_argument("--dry-run", action="store_true", help="Print actions without executing")

    sync = sub.add_parser("sync", help="Federated sync: file bundles, peer HTTP endpoints, or the whole mesh")
    sync.add_argument("action", choices=["export", "import", "pull", "push", "auto"])
    sync.add_argument(
        "target", nargs="?", default=None,
        help="Bundle .jsonl path (export/import) or peer base URL (pull/push); omit for auto",
    )
    sync.add_argument("--since", default=None, help="Only records updated after this ISO timestamp")
    sync.add_argument("--peer-token", default=None, help="Bearer token of the peer's Web API")
    sync.add_argument("--team", default=None, help="Export only one team/project's shared memory")

    peers = sub.add_parser("peers", help="Manage federated sync peers")
    peers.add_argument("action", choices=["add", "remove", "list"])
    peers.add_argument("url", nargs="?", default=None)
    peers.add_argument("--peer-token", default=None, help="Bearer token of the peer's Web API")

    retention = sub.add_parser("retention", help="Archive expired and deeply-decayed memories")
    retention.add_argument(
        "--half-lives", type=float, default=None,
        help="Also archive unpinned memories idle for N decay half-lives (default 4; 0 = expired only)",
    )
    return p


def _cmd_service(args) -> int:
    from . import service as svc

    config = svc.make_config(args.home, args.host, args.port)
    if args.action == "install":
        actions = svc.install(config, dry_run=args.dry_run)
        for action in actions:
            print(("would: " if args.dry_run else "") + action)
        if not args.dry_run:
            print(f"installed — console at http://{args.host}:{args.port}/ (starts at login)")
        return 0
    if args.action == "uninstall":
        for action in svc.uninstall(dry_run=args.dry_run):
            print(("would: " if args.dry_run else "") + action)
        return 0
    result = svc.control(args.action)
    output = (result.stdout or result.stderr or "").strip()
    if output:
        print(output.splitlines()[0] if args.action == "status" else output)
    print(f"{args.action}: {'ok' if result.returncode == 0 else 'not running / not installed'}")
    return 0 if result.returncode == 0 else 1


def _cmd_token(args) -> int:
    from . import tokens

    existing = tokens.load_token(args.home)
    if args.action == "show":
        if existing is None:
            print("no token set — run: agent-memory token create")
            return 1
        print(existing)
        return 0
    if args.action == "disable":
        if tokens.delete_token(args.home):
            print("token removed — the Web UI API is now open (localhost-only recommended)")
        else:
            print("no token was set")
        return 0
    if args.action == "create" and existing is not None:
        print("a token already exists — use `agent-memory token rotate` to replace it,")
        print("or `agent-memory token show` to display it")
        return 1
    token = tokens.create_token(args.home)
    print(f"Web UI token saved to {tokens.token_path(args.home)} (mode 600):")
    print()
    print(f"  {token}")
    print()
    print("agent-memory-web now requires this token on every /api/ route.")
    print("The Web UI will prompt for it on first use.")
    return 0


def _cmd_doctor(args) -> int:
    import importlib.util
    import sqlite3
    import subprocess
    import sys

    from . import tokens

    def present(module: str) -> bool:
        return importlib.util.find_spec(module) is not None

    checks = {
        "api": (["fastapi", "uvicorn"], "Web UI (agent-memory-web)"),
        "mcp": (["mcp"], "MCP server for agent integration"),
        "semantic": (["numpy", "turbovec"], "turbovec semantic vector recall"),
    }
    fts_ok = True
    try:
        probe = sqlite3.connect(":memory:")
        probe.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        probe.close()
    except sqlite3.OperationalError:
        fts_ok = False
    print(f"[{'ok' if fts_ok else 'FAIL'}] SQLite FTS5 (required)")

    missing_extras: list[str] = []
    for extra, (modules, description) in checks.items():
        ok = all(present(module) for module in modules)
        print(f"[{'ok' if ok else 'missing'}] {extra}: {description}")
        if not ok:
            missing_extras.append(extra)

    from .agents_config import config_path, load_agents_config

    try:
        configured = load_agents_config(args.home)
        print(f"[{'ok' if configured else 'none'}] agents.toml "
              f"({len(configured)} agents declared at {config_path(args.home)})"
              if configured else
              f"[none] agents.toml (optional; declare your fleet at {config_path(args.home)})")
    except ValueError as exc:
        print(f"[FAIL] agents.toml: {exc}")

    token_set = tokens.load_token(args.home) is not None
    print(f"[{'ok' if token_set else 'none'}] Web UI token "
          f"({'set' if token_set else 'run: agent-memory token create'})")

    if missing_extras:
        spec = f"agent-memory-os[{','.join(missing_extras)}]"
        if args.install:
            print(f"installing: {spec}")
            result = subprocess.run([sys.executable, "-m", "pip", "install", spec])
            return result.returncode
        print()
        print(f"install everything missing with: pip install '{spec}'")
        print("or re-run: agent-memory doctor --install")
        return 1
    if not fts_ok:
        return 1
    print("all good.")
    return 0


def _cmd_backup(args) -> int:
    import sqlite3
    from pathlib import Path

    from .tokens import resolve_home

    db_path = resolve_home(args.home) / "memories.db"
    if not db_path.exists():
        print(f"no database at {db_path}")
        return 1
    dest = Path(args.dest).expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(db_path)
    target = sqlite3.connect(dest)
    try:
        # sqlite3 online backup: consistent even while another process writes (WAL)
        source.backup(target)
    finally:
        target.close()
        source.close()
    print(f"backed up {db_path} -> {dest}")
    return 0


def _cmd_restore(args) -> int:
    import sqlite3
    from pathlib import Path

    from .tokens import resolve_home

    src = Path(args.src).expanduser()
    if not src.exists():
        print(f"backup not found: {src}")
        return 1
    db_path = resolve_home(args.home) / "memories.db"
    if db_path.exists() and not args.force:
        print(f"database already exists at {db_path} — pass --force to overwrite")
        return 1
    db_path.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(src)
    target = sqlite3.connect(db_path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    print(f"restored {src} -> {db_path}")
    print("disposable indexes rebuild automatically; run `agent-memory stats` to verify")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "service":
        return _cmd_service(args)
    if args.command == "token":
        return _cmd_token(args)
    if args.command == "doctor":
        return _cmd_doctor(args)
    if args.command == "backup":
        return _cmd_backup(args)
    if args.command == "restore":
        return _cmd_restore(args)
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
        if args.command == "check":
            report = client.integrity_check()
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            return 0 if report["ok"] else 1
        if args.command == "peers":
            if args.action == "list":
                print(json.dumps(client.store.list_peers(), ensure_ascii=False, indent=2))
                return 0
            if not args.url:
                print("peers add/remove require a URL")
                return 2
            if args.action == "add":
                print(json.dumps(client.store.add_peer(args.url, token=args.peer_token)))
            else:
                removed = client.store.remove_peer(args.url)
                print("removed" if removed else "not registered")
            return 0
        if args.command == "sync":
            if args.action == "auto":
                from .sync import sync_all_peers

                print(json.dumps(sync_all_peers(client), ensure_ascii=False, indent=2))
                return 0
            if not args.target:
                print("sync export/import/pull/push require a target")
                return 2
            if args.action == "export":
                report = client.export_bundle(args.target, since=args.since, team=args.team)
            elif args.action == "import":
                report = client.import_bundle(args.target)
            else:
                from .sync import pull_from_peer, push_to_peer

                if args.action == "pull":
                    report = pull_from_peer(
                        client, args.target, since=args.since, peer_token=args.peer_token
                    )
                else:
                    report = push_to_peer(
                        client, args.target, since=args.since, peer_token=args.peer_token
                    )
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "retention":
            if args.half_lives is None:
                result = client.run_retention()
            else:
                result = client.run_retention(decayed_half_lives=args.half_lives or None)
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
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
