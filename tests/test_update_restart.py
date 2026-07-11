"""update command: post-upgrade handling of already-running processes.

A pip upgrade rewrites files on disk but never touches live processes — the
web console and MCP servers keep serving the old code until restarted. The
update tool must restart the console (it owns it) and report MCP servers
(owned by their host app, e.g. Claude Code).
"""

from __future__ import annotations

import argparse

from agent_memory_os import cli


def _args(**over):
    base = {"check": False, "yes": True, "no_restart": False, "home": None}
    base.update(over)
    return argparse.Namespace(**base)


# ---------- etime parsing ----------

def test_parse_etime_mm_ss():
    assert cli._parse_etime("05:31") == 5 * 60 + 31


def test_parse_etime_hh_mm_ss():
    assert cli._parse_etime("03:05:31") == 3 * 3600 + 5 * 60 + 31


def test_parse_etime_dd_hh_mm_ss():
    assert cli._parse_etime("2-03:05:31") == 2 * 86400 + 3 * 3600 + 5 * 60 + 31


def test_parse_etime_garbage():
    assert cli._parse_etime("running") is None
    assert cli._parse_etime("") is None


# ---------- process discovery ----------

PS_OUTPUT = """\
  501 /usr/libexec/foo
  60230 /venv/bin/python /venv/bin/agent-memory-web --home /Users/x/.agent-memory
  49259 /venv/bin/python -m agent_memory_os.mcp_server
  70000 vim src/agent_memory_os/cli.py
  70001 /Applications/Claude.app/claude --mcp-config {"command":"python","args":["-m","agent_memory_os.mcp_server"]}
  70002 grep agent-memory-web
"""


def test_running_amos_processes_parses_web_and_mcp(monkeypatch):
    import subprocess as sp

    monkeypatch.setattr(sp, "check_output", lambda *a, **k: PS_OUTPUT)
    procs = cli._running_amos_processes()
    kinds = {(pid, kind) for pid, kind, _ in procs}
    assert (60230, "web") in kinds
    assert (49259, "mcp") in kinds
    # unrelated processes are not matched, even when they merely MENTION the
    # module (host apps like Claude Code carry it in a config argument) or
    # are inspection tools like vim/grep
    matched = {pid for pid, _, _ in procs}
    assert matched.isdisjoint({70000, 70001, 70002})


def test_classify_windows_exe_wrapper():
    assert cli._classify_amos_cmdline(
        r"C:\venv\Scripts\agent-memory-web.exe --home C:\data"
    ) == "web"


def test_running_amos_processes_survives_ps_failure(monkeypatch):
    import subprocess as sp

    def boom(*a, **k):
        raise OSError("no ps")

    monkeypatch.setattr(sp, "check_output", boom)
    assert cli._running_amos_processes() == []


# ---------- staleness ----------

def test_stale_amos_processes_flags_pre_install_starts(monkeypatch):
    now = 1_000_000.0
    monkeypatch.setattr(cli, "_install_mtime", lambda: now)
    monkeypatch.setattr(
        cli, "_running_amos_processes",
        lambda: [(1, "web", "agent-memory-web"), (2, "mcp", "python -m agent_memory_os.mcp_server")],
    )
    # pid 1 started long before the install; pid 2 after it
    starts = {1: now - 3600, 2: now + 60}
    monkeypatch.setattr(cli, "_proc_start_ts", lambda pid: starts[pid])
    stale = cli._stale_amos_processes()
    assert [(p, k) for p, k, _ in stale] == [(1, "web")]


def test_stale_amos_processes_unknown_start_not_flagged(monkeypatch):
    monkeypatch.setattr(cli, "_install_mtime", lambda: 1_000_000.0)
    monkeypatch.setattr(cli, "_running_amos_processes", lambda: [(1, "web", "agent-memory-web")])
    monkeypatch.setattr(cli, "_proc_start_ts", lambda pid: None)
    assert cli._stale_amos_processes() == []


# ---------- post-upgrade handling ----------

def test_handle_running_processes_restarts_web_and_reports_mcp(monkeypatch, capsys):
    monkeypatch.setattr(
        cli, "_running_amos_processes",
        lambda: [(11, "web", "agent-memory-web --home /h"), (22, "mcp", "python -m agent_memory_os.mcp_server")],
    )
    monkeypatch.setattr(cli, "_web_service_installed", lambda: False)
    seen = []
    monkeypatch.setattr(cli, "_restart_web_from_pidfile",
                        lambda home: seen.append(home) or "restarted (new pid 999)")
    cli._handle_running_processes(assume_yes=True, no_restart=False, home="/h")
    out = capsys.readouterr().out
    assert seen == ["/h"]
    assert "restarted" in out
    assert "Claude Code" in out  # MCP restart-the-host-app notice


def test_handle_running_processes_no_restart_flag(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_running_amos_processes", lambda: [(11, "web", "agent-memory-web")])
    called = []
    monkeypatch.setattr(cli, "_restart_web_from_pidfile", lambda home: called.append(home) or "x")
    cli._handle_running_processes(assume_yes=True, no_restart=True)
    assert called == []
    assert "NOT restarted" in capsys.readouterr().out


def test_handle_running_processes_prefers_installed_service(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_running_amos_processes", lambda: [(11, "web", "agent-memory-web")])
    monkeypatch.setattr(cli, "_web_service_installed", lambda: True)
    import types

    from agent_memory_os import service as svc

    calls = []

    def fake_control(action):
        calls.append(action)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(svc, "control", fake_control)
    cli._handle_running_processes(assume_yes=True, no_restart=False)
    assert calls == ["restart"]
    assert "service restart: ok" in capsys.readouterr().out


def test_handle_running_processes_quiet_when_nothing_runs(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_running_amos_processes", lambda: [])
    cli._handle_running_processes(assume_yes=True, no_restart=False)
    assert capsys.readouterr().out == ""


# ---------- pidfile-based restart (security: never re-exec a ps-derived argv) ----------

def test_restart_from_pidfile_missing_returns_manual(tmp_path):
    # No pidfile written → must not signal or exec anything.
    assert "manually" in cli._restart_web_from_pidfile(str(tmp_path))


def test_restart_from_pidfile_dead_pid_not_relaunched(tmp_path, monkeypatch):
    from agent_memory_os.pidfile import write_web_pidfile

    # Record a pidfile whose pid is not alive; os.kill(pid,0) → ProcessLookupError.
    write_web_pidfile(str(tmp_path), argv=["/bin/true"], cwd=str(tmp_path))
    launched = []
    import os as _os
    import subprocess as sp
    monkeypatch.setattr(sp, "Popen", lambda *a, **k: launched.append(a))

    def fake_kill(pid, sig):
        raise ProcessLookupError

    monkeypatch.setattr(_os, "kill", fake_kill)
    msg = cli._restart_web_from_pidfile(str(tmp_path))
    assert "not running" in msg
    assert launched == []  # never relaunched a dead/spoofable target


def test_pidfile_roundtrip_rejects_garbage(tmp_path):
    from agent_memory_os.pidfile import pidfile_path, read_web_pidfile, write_web_pidfile

    write_web_pidfile(str(tmp_path), argv=["/usr/bin/x", "--home", str(tmp_path)])
    rec = read_web_pidfile(str(tmp_path))
    assert isinstance(rec["pid"], int) and rec["argv"][0] == "/usr/bin/x"
    pidfile_path(str(tmp_path)).write_text("not json", encoding="utf-8")
    assert read_web_pidfile(str(tmp_path)) is None


# ---------- update flow wiring ----------

def test_update_already_latest_warns_about_stale_processes(monkeypatch, capsys):
    from importlib.metadata import version

    current = version("agent-memory-os")
    monkeypatch.setattr(cli, "_pypi_latest", lambda pkg: current)
    monkeypatch.setattr(
        cli, "_stale_amos_processes",
        lambda: [(99, "mcp", "python -m agent_memory_os.mcp_server")],
    )
    rc = cli._cmd_update(_args(check=True))
    out = capsys.readouterr().out
    assert rc == 0
    assert "Already on the latest version." in out
    assert "still running older code" in out
    assert "restart the host app" in out.lower()


def test_update_upgrade_success_triggers_process_handling(monkeypatch, capsys):
    import subprocess as sp

    monkeypatch.setattr(cli, "_pypi_latest", lambda pkg: "999.0.0")
    monkeypatch.setattr(cli, "_in_docker", lambda: False)
    monkeypatch.setattr(sp, "call", lambda cmd: 0)
    handled = []
    monkeypatch.setattr(
        cli, "_handle_running_processes",
        lambda **kw: handled.append(kw),
    )
    rc = cli._cmd_update(_args(yes=True))
    assert rc == 0
    assert handled == [{"assume_yes": True, "no_restart": False, "home": None}]


def test_update_upgrade_failure_skips_process_handling(monkeypatch):
    import subprocess as sp

    monkeypatch.setattr(cli, "_pypi_latest", lambda pkg: "999.0.0")
    monkeypatch.setattr(cli, "_in_docker", lambda: False)
    monkeypatch.setattr(sp, "call", lambda cmd: 1)
    monkeypatch.setattr(
        cli, "_handle_running_processes",
        lambda **kw: (_ for _ in ()).throw(AssertionError("must not run on failed upgrade")),
    )
    assert cli._cmd_update(_args(yes=True)) == 1
