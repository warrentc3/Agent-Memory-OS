from __future__ import annotations

import argparse
import json
from pathlib import Path

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
    service.add_argument("action", choices=["install", "uninstall", "start", "stop", "restart", "status"])
    service.add_argument("--host", default=None, help="Bind host (default: instance.toml or 127.0.0.1)")
    service.add_argument("--port", type=int, default=None, help="Bind port (default: instance.toml or 8000)")
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
    peers.add_argument(
        "--policy", dest="peer_policy", default="shared",
        help="What to sync to this peer: 'shared' (no private memory, default), "
             "'full' (whole store — own trusted nodes only), or 'team:<id>'",
    )
    peers.add_argument(
        "--name", dest="peer_name", default="",
        help="Friendly name for this peer (auto-fetched from the peer if omitted)",
    )

    node = sub.add_parser("node", help="Show or set this instance's identity and Web UI port")
    node.add_argument("--set-name", default=None, help="Set node_name (shown to peers during sync)")
    node.add_argument("--set-host", default=None, help="Set the Web UI bind host")
    node.add_argument("--set-port", type=int, default=None, help="Set the Web UI port")

    team = sub.add_parser("team", help="Manage teams and their node members")
    team.add_argument("action", choices=["list", "create", "delete", "add-member", "remove-member"])
    team.add_argument("team_id", nargs="?", default=None)
    team.add_argument("agent_id", nargs="?", default=None)
    team.add_argument("--name", default="", help="Display name (create)")

    project = sub.add_parser("project", help="Manage projects under a team (members ⊆ team)")
    project.add_argument("action", choices=["list", "create", "delete", "add-member", "remove-member"])
    project.add_argument("project_id", nargs="?", default=None)
    project.add_argument("agent_id", nargs="?", default=None)
    project.add_argument("--team", dest="team_id", default=None, help="Team id (create / list filter)")
    project.add_argument("--name", default="", help="Display name (create)")

    maint = sub.add_parser("maintenance", help="Ops maintenance: health scan, orphan cleanup, reindex, vacuum")
    maint.add_argument("action", choices=["scan", "orphans", "reindex", "vacuum"])
    maint.add_argument("--delete", action="store_true", help="orphans: delete them (default lists)")

    update = sub.add_parser("update", help="Check for and install a newer version (host or Docker)")
    update.add_argument("--check", action="store_true", help="Only report the latest version; don't install")
    update.add_argument("--yes", action="store_true", help="Install without prompting (host/pip only)")
    update.add_argument("--no-restart", action="store_true",
                        help="After upgrading, do not restart the running web console")

    retention = sub.add_parser("retention", help="Archive expired and deeply-decayed memories")
    retention.add_argument(
        "--half-lives", type=float, default=None,
        help="Also archive unpinned memories idle for N decay half-lives (default 4; 0 = expired only)",
    )
    return p


def _cmd_service(args) -> int:
    from . import service as svc
    from .settings import load_instance_settings

    settings = load_instance_settings(args.home)
    host = args.host or settings.host
    port = args.port if args.port is not None else settings.port
    config = svc.make_config(args.home, host, port)
    if args.action == "install":
        actions = svc.install(config, dry_run=args.dry_run)
        for action in actions:
            print(("would: " if args.dry_run else "") + action)
        if not args.dry_run:
            print(f"installed — console at http://{host}:{port}/ (starts at login)")
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


def _report_orphans(client) -> None:
    """After a member removal, warn if any memory is now reachable by nobody."""
    n = client.orphan_count()
    if n:
        print(f"note: {n} memory(ies) are now orphaned (scoped to a group with no "
              f"members — visible only to admin). Review: agent-memory maintenance "
              f"orphans   |   clean: agent-memory maintenance orphans --delete")


def _in_docker() -> bool:
    if Path("/.dockerenv").exists():
        return True
    try:
        return "docker" in Path("/proc/1/cgroup").read_text()
    except OSError:
        return False


_PYPI_LAST_ERROR: str | None = None


def _pypi_latest(pkg: str) -> str | None:
    global _PYPI_LAST_ERROR
    import urllib.request
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{pkg}/json", timeout=6) as resp:
            _PYPI_LAST_ERROR = None
            return json.load(resp)["info"]["version"]
    except Exception as exc:  # noqa: BLE001 - offline / unreachable is a normal outcome
        _PYPI_LAST_ERROR = f"{type(exc).__name__}: {exc}"
        return None


def _running_amos_processes() -> list[tuple[int, str, str]]:
    """Find running AgentMemoryOS processes: (pid, kind, cmdline).

    kind is "web" (console, restartable by us) or "mcp" (stdio child owned by a
    host app such as Claude Code — never killed here, only reported).
    """
    import os
    import subprocess
    import sys

    try:
        if sys.platform == "win32":
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command",
                 'Get-CimInstance Win32_Process | ForEach-Object { "$($_.ProcessId)`t$($_.CommandLine)" }'],
                text=True, timeout=10)
            rows = [line.split("\t", 1) for line in out.splitlines() if "\t" in line]
        else:
            out = subprocess.check_output(["ps", "-axo", "pid=,command="], text=True, timeout=10)
            rows = [line.strip().split(None, 1) for line in out.splitlines() if line.strip()]
    except Exception:  # noqa: BLE001 - process listing is best-effort
        return []
    me = os.getpid()
    procs: list[tuple[int, str, str]] = []
    for row in rows:
        if len(row) != 2:
            continue
        pid_s, cmd = row
        try:
            pid = int(pid_s)
        except ValueError:
            continue
        if pid == me:
            continue
        kind = _classify_amos_cmdline(cmd)
        if kind:
            procs.append((pid, kind, cmd.strip()))
    return procs


def _classify_amos_cmdline(cmd: str) -> str | None:
    """"web" / "mcp" / None for a raw process command line.

    Token-exact matching: host apps (e.g. Claude Code) can carry the module
    name inside a config argument without BEING the server — substring
    matching would misreport them as restart targets.
    """
    tokens = cmd.split()
    if not tokens:
        return None

    def _basename(token: str) -> str:
        return token.replace("\\", "/").rsplit("/", 1)[-1].removesuffix(".exe")

    interp = _basename(tokens[0]).lower()
    if interp in ("grep", "egrep", "fgrep", "rg", "less", "more", "tail", "vim", "nano"):
        return None
    is_python = "python" in interp
    basenames = [_basename(t) for t in tokens]
    module_pairs = {
        (tokens[i], tokens[i + 1]) for i in range(len(tokens) - 1)
    }
    if "agent-memory-web" in basenames or (
        is_python and ("-m", "agent_memory_os.web_app") in module_pairs
    ):
        return "web"
    if is_python and ("-m", "agent_memory_os.mcp_server") in module_pairs:
        return "mcp"
    return None


def _parse_etime(etime: str) -> int | None:
    """ps etime ([[dd-]hh:]mm:ss) -> elapsed seconds."""
    import re

    m = re.match(r"^(?:(?:(\d+)-)?(\d+):)?(\d+):(\d+)$", etime.strip())
    if not m:
        return None
    d, h, mn, s = (int(x) if x else 0 for x in m.groups())
    return ((d * 24 + h) * 60 + mn) * 60 + s


def _proc_start_ts(pid: int) -> float | None:
    import subprocess
    import sys
    import time

    if sys.platform == "win32":
        return None  # unknown -> caller treats as not-provably-stale
    try:
        out = subprocess.check_output(["ps", "-p", str(pid), "-o", "etime="], text=True, timeout=5)
    except Exception:  # noqa: BLE001
        return None
    elapsed = _parse_etime(out)
    return None if elapsed is None else time.time() - elapsed


def _install_mtime() -> float | None:
    """When the installed package files were last written (== install/upgrade time)."""
    try:
        import agent_memory_os

        return Path(agent_memory_os.__file__).stat().st_mtime
    except Exception:  # noqa: BLE001
        return None


def _stale_amos_processes() -> list[tuple[int, str, str]]:
    """Running processes that started before the current install landed on disk."""
    installed = _install_mtime()
    if installed is None:
        return []
    stale = []
    for pid, kind, cmd in _running_amos_processes():
        started = _proc_start_ts(pid)
        # 90s slack absorbs ps's minute-resolution etime.
        if started is not None and started < installed - 90:
            stale.append((pid, kind, cmd))
    return stale


def _restart_web_from_pidfile(home) -> str:
    """Restart the console recorded in <home>/web.pid.

    SECURITY: the relaunch argv comes from the pidfile that the console wrote
    about ITSELF — never from `ps` output, which any local process could spoof
    into being re-executed. Only the recorded pid is signalled, and only if it
    is actually alive. Returns a short status string for the caller to print.
    """
    import os
    import signal
    import subprocess
    import sys
    import time

    from .pidfile import read_web_pidfile
    from .tokens import resolve_home

    rec = read_web_pidfile(home)
    if not rec:
        return "no pidfile — restart the console manually"
    pid, argv, cwd = rec["pid"], rec["argv"], rec.get("cwd") or None
    if sys.platform == "win32":
        return "automatic restart unsupported on Windows — restart the console manually"
    try:
        os.kill(pid, 0)  # is the recorded process actually alive & signal-able?
    except ProcessLookupError:
        return f"recorded pid {pid} is not running — start the console manually"
    except PermissionError:
        return f"recorded pid {pid} not owned by this user — restart it manually"
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return f"could not signal pid {pid} — restart the console manually"
    for _ in range(40):  # up to ~10s for the port to be released
        try:
            os.kill(pid, 0)
        except OSError:
            break
        time.sleep(0.25)
    stdout = subprocess.DEVNULL
    stderr = subprocess.DEVNULL
    try:
        log = open(Path(resolve_home(home)) / "web.log", "ab")  # noqa: SIM115 - handed to child
        stdout, stderr = log, subprocess.STDOUT
    except OSError:
        pass
    try:
        child = subprocess.Popen(argv, cwd=cwd, stdout=stdout, stderr=stderr,
                                 start_new_session=True)
    except Exception as exc:  # noqa: BLE001
        return f"relaunch failed ({exc}) — restart the console manually"
    time.sleep(1.0)  # liveness: confirm the new process didn't immediately die
    if child.poll() is not None:
        return (f"relaunched process exited (code {child.returncode}) — the old "
                f"port may still be held; restart the console manually")
    return f"restarted (new pid {child.pid})"


def _web_service_installed() -> bool:
    import subprocess
    import sys

    from . import service as svc

    if sys.platform == "win32":
        # No unit file — query the scheduled task instead.
        try:
            return subprocess.run(
                ["schtasks", "/Query", "/TN", svc.SERVICE_NAME],
                capture_output=True, timeout=10,
            ).returncode == 0
        except Exception:  # noqa: BLE001
            return False
    try:
        return svc._unit_path(sys.platform).exists()
    except Exception:  # noqa: BLE001
        return False


def _handle_running_processes(*, assume_yes: bool, no_restart: bool, home=None) -> None:
    """Post-upgrade cleanup: everything still running loads the OLD code."""
    procs = _running_amos_processes()
    web = [p for p in procs if p[1] == "web"]
    mcp = [p for p in procs if p[1] == "mcp"]
    if not web and not mcp:
        return
    print("\nRunning processes still loaded with the previous version:")
    for pid, kind, cmd in web + mcp:
        print(f"  [{kind}] pid {pid}: {cmd[:100]}")
    if web:
        if no_restart:
            print("Web console NOT restarted (--no-restart). Restart it to load the new version.")
        elif _web_service_installed():
            from . import service as svc

            result = svc.control("restart")
            print(f"web console service restart: {'ok' if result.returncode == 0 else 'failed'}")
        else:
            do_restart = assume_yes
            if not do_restart:
                try:
                    resp = input("Restart the web console now to load the new version? [Y/n] ").strip().lower()
                except EOFError:
                    resp = "n"
                do_restart = resp in ("", "y", "yes")
            if do_restart:
                print(f"web console: {_restart_web_from_pidfile(home)}")
            else:
                print("Skipped. Restart the web console manually to load the new version.")
    if mcp:
        print("MCP server(s) are owned by their host app and were not touched.")
        print("Restart the host app (e.g. Claude Code) to load the new version.")


def _warn_stale_processes() -> None:
    """`update --check` / already-latest path: disk is current, memory may not be."""
    stale = _stale_amos_processes()
    if not stale:
        return
    print("\nNote: these processes started BEFORE the installed version landed and are")
    print("likely still running older code (a pip upgrade never touches live processes):")
    for pid, kind, cmd in stale:
        print(f"  [{kind}] pid {pid}: {cmd[:100]}")
    if any(k == "web" for _, k, _ in stale):
        print("Web console: restart it (agent-memory service restart, or kill + relaunch).")
    if any(k == "mcp" for _, k, _ in stale):
        print("MCP server: restart the host app (e.g. Claude Code).")


def _cmd_update(args) -> int:
    import platform
    import subprocess
    import sys
    from importlib.metadata import PackageNotFoundError, version

    try:
        current = version("agent-memory-os")
    except PackageNotFoundError:
        current = "unknown"
    docker = _in_docker()
    latest = _pypi_latest("agent-memory-os")
    print(f"current:    {current}")
    print(f"latest:     {latest or 'unknown (could not reach PyPI)'}")
    print(f"platform:   {platform.system()} {platform.machine()}")
    print(f"deployment: {'Docker container' if docker else 'host (pip)'}")
    if not latest:
        print(f"Could not reach PyPI ({_PYPI_LAST_ERROR or 'unknown error'}).")
        if _PYPI_LAST_ERROR and "CERTIFICATE" in _PYPI_LAST_ERROR.upper():
            print("Your Python is missing CA certificates. Fix with:  pip install -U certifi")
            print("(on macOS you may also need to run the 'Install Certificates.command' for your Python).")
        return 1
    if latest == current:
        print("Already on the latest version.")
        _warn_stale_processes()
        return 0
    print(f"\nA newer version is available: {current} -> {latest}")
    if args.check:
        _warn_stale_processes()
        return 0
    if docker:
        # A container can't pip-upgrade itself in place; guide the host update.
        print("\nDocker deployment — update by pulling the new image and recreating:")
        print(f"  docker pull yamantaka520/agent-memory-os:{latest}")
        print("  docker compose up -d          # or re-run docker run with the new tag")
        print("Data in the /data volume persists; migrations self-apply on start.")
        return 0
    if not args.yes:
        try:
            resp = input(f"Upgrade agent-memory-os {current} -> {latest} via pip now? [y/N] ").strip().lower()
        except EOFError:
            resp = ""
        if resp not in ("y", "yes"):
            print("Aborted. Run with --yes to skip this prompt.")
            return 0
    cmd = [sys.executable, "-m", "pip", "install", "-U", "agent-memory-os[full]"]
    print("running:", " ".join(cmd))
    rc = subprocess.call(cmd)
    if rc == 0:
        _handle_running_processes(
            assume_yes=args.yes, no_restart=args.no_restart, home=args.home,
        )
    return rc


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "update":
        return _cmd_update(args)
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
        if args.command == "node":
            from .settings import load_instance_settings, update_instance_settings

            if args.set_name is not None or args.set_host is not None or args.set_port is not None:
                settings = update_instance_settings(
                    args.home, node_name=args.set_name, host=args.set_host, port=args.set_port
                )
            else:
                settings = load_instance_settings(args.home)
            print(json.dumps({
                "node_name": settings.node_name, "host": settings.host, "port": settings.port,
            }, ensure_ascii=False, indent=2))
            return 0
        if args.command == "team":
            s = client.store
            if args.action == "list":
                print(json.dumps(s.list_teams(), ensure_ascii=False, indent=2))
            elif args.action == "create":
                if not args.team_id:
                    print("team create requires a team id"); return 2
                print(json.dumps(s.create_team(args.team_id, name=args.name), ensure_ascii=False))
            elif args.action == "delete":
                print("deleted" if s.delete_team(args.team_id) else "not found")
            elif args.action in ("add-member", "remove-member"):
                if not (args.team_id and args.agent_id):
                    print(f"team {args.action} requires <team_id> <agent_id>"); return 2
                if args.action == "add-member":
                    s.add_team_member(args.team_id, args.agent_id)
                else:
                    s.remove_team_member(args.team_id, args.agent_id)
                    _report_orphans(client)
                print(json.dumps(s.get_team(args.team_id), ensure_ascii=False))
            return 0
        if args.command == "project":
            s = client.store
            if args.action == "list":
                print(json.dumps(s.list_projects(args.team_id), ensure_ascii=False, indent=2))
            elif args.action == "create":
                if not (args.project_id and args.team_id):
                    print("project create requires <project_id> --team <team_id>"); return 2
                print(json.dumps(s.create_project(args.project_id, args.team_id, name=args.name), ensure_ascii=False))
            elif args.action == "delete":
                print("deleted" if s.delete_project(args.project_id) else "not found")
            elif args.action in ("add-member", "remove-member"):
                if not (args.project_id and args.agent_id):
                    print(f"project {args.action} requires <project_id> <agent_id>"); return 2
                if args.action == "add-member":
                    s.add_project_member(args.project_id, args.agent_id)
                else:
                    s.remove_project_member(args.project_id, args.agent_id)
                    _report_orphans(client)
                print(json.dumps(s.get_project(args.project_id), ensure_ascii=False))
            return 0
        if args.command == "maintenance":
            if args.action == "scan":
                print(json.dumps(client.maintenance_scan(), ensure_ascii=False, indent=2))
            elif args.action == "orphans":
                orphans = client.find_orphan_memories()
                if args.delete:
                    print(json.dumps(client.delete_orphan_memories(), ensure_ascii=False))
                else:
                    print(f"{len(orphans)} orphan memories (scoped to an empty/deleted group):")
                    for o in orphans[:50]:
                        print(f"  {o['id']}  {o['visibility']}  {o['content']!r}")
                    if orphans:
                        print("delete them with: agent-memory maintenance orphans --delete")
            elif args.action == "reindex":
                print(json.dumps(client.rebuild_indexes(), ensure_ascii=False))
            elif args.action == "vacuum":
                print(json.dumps(client.vacuum(), ensure_ascii=False))
            return 0
        if args.command == "peers":
            if args.action == "list":
                print(json.dumps(client.store.list_peers(), ensure_ascii=False, indent=2))
                return 0
            if not args.url:
                print("peers add/remove require a URL")
                return 2
            if args.action == "add":
                name = args.peer_name.strip()
                if not name:
                    from .sync import fetch_peer_node_name
                    name = fetch_peer_node_name(args.url, token=args.peer_token)
                print(json.dumps(client.store.add_peer(
                    args.url, token=args.peer_token, policy=args.peer_policy, name=name
                )))
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
    except (ValueError, KeyError) as exc:
        # Domain errors (e.g. subset violation, missing team/project) should
        # print a friendly message and a non-zero exit, not a raw traceback.
        print(f"error: {exc}")
        return 2
    finally:
        client.close()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
