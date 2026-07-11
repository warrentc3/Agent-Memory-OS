"""Upgrade-path smoke check for CI.

`--seed`   : create a DB (with team-scoped data if the installed version supports
             it) using whatever agent-memory-os is installed — run under the LAST
             PUBLISHED release.
`--verify` : reopen the same DB under the working tree; assert migrations applied
             forward, integrity holds, and the seeded memory survived.

Run the two phases with different installs against the same AGENT_MEMORY_HOME.
"""

from __future__ import annotations

import sys

from agent_memory_os import MemoryClient


def seed(home: str) -> int:
    c = MemoryClient(home=home)
    c.store.register_agent("a1")
    try:
        c.store.create_team("t")
        c.store.add_team_member("t", "a1")
        c.add("upgrade survivor", owner="a1", visibility=["team:t"])
    except Exception:  # older release without first-class teams
        c.add("upgrade survivor", owner="a1", visibility=["global"])
    print(f"seeded at schema {c.store.schema_version()}")
    return 0


def verify(home: str) -> int:
    c = MemoryClient(home=home)
    if not c.integrity_check()["ok"]:
        print("FAIL: integrity_check after upgrade")
        return 1
    hits = c.search("survivor", requester_agent_id="a1")
    if not any("survivor" in h.record.content for h in hits):
        print("FAIL: seeded memory lost across upgrade")
        return 1
    cols = {r[1] for r in c.store.conn.execute("PRAGMA table_info(memories)")}
    if "acl_updated_at" not in cols:
        print("FAIL: migration 15 (acl clock) did not apply")
        return 1
    print(f"OK: upgraded to schema {c.store.schema_version()}, data + integrity intact")
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    home = sys.argv[2] if len(sys.argv) > 2 else "/tmp/amos-upgrade"
    if mode == "--seed":
        raise SystemExit(seed(home))
    if mode == "--verify":
        raise SystemExit(verify(home))
    print("usage: upgrade_smoke.py --seed|--verify [home]")
    raise SystemExit(2)
