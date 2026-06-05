import subprocess
import sys


def test_cli_add_search_pack(tmp_path):
    base = [sys.executable, "-m", "agent_memory_os.cli", "--home", str(tmp_path)]
    add = subprocess.run(base + ["add", "Reports use UTC+8 Taipei timestamps", "--owner", "bastet-agent", "--tag", "reports"], check=True, text=True, capture_output=True)
    assert add.stdout.strip().startswith("mem_")

    search = subprocess.run(base + ["search", "Taipei timestamps", "--owner", "bastet-agent"], check=True, text=True, capture_output=True)
    assert "Taipei" in search.stdout

    pack = subprocess.run(base + ["pack", "report timestamp preference", "--owner", "bastet-agent", "--max-tokens", "100"], check=True, text=True, capture_output=True)
    assert "MEMORY CONTEXT PACK" in pack.stdout
