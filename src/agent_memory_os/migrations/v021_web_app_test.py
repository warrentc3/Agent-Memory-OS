"""Direct timestamp contract for the v21 web-expiry test shape.

The active web API test carries the v22 canonical stamp contract. This test
preserves its formerly accepted v21 offset-seconds expiry at the migration
boundary.
"""

import re
import sqlite3

from agent_memory_os.migrations.v022_timestamp_ubiquity import migrate

V21_EXPIRY = "2030-01-01T00:00:00+00:00"
V21_WEB_UI_EXPIRY = "2030-01-01T00:00:00.000Z"
_V21_CLOCK = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+00:00"
)
_V21_WEB_UI_CLOCK = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z"
)


def test_v21_web_expiry_shape_crosses_into_v22() -> None:
    """Execution contract: web expiry input crossing v21 -> v22.

    Provenance: active behavior introduced at c70a11f7 before the migration
    registry.
    Input scope: the v21 ``expires_at`` value formerly accepted as the valid
    branch of the web API timestamp-validation test.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE memories (id TEXT PRIMARY KEY, expires_at TEXT)")
    conn.execute(
        "INSERT INTO memories(id, expires_at) VALUES ('web', ?)",
        (V21_EXPIRY,),
    )
    conn.execute(
        "INSERT INTO memories(id, expires_at) VALUES ('web-ui', ?)",
        (V21_WEB_UI_EXPIRY,),
    )

    assert _V21_CLOCK.fullmatch(V21_EXPIRY)
    assert _V21_WEB_UI_CLOCK.fullmatch(V21_WEB_UI_EXPIRY)

    migrate(conn)
    migrate(conn)

    migrated = dict(conn.execute("SELECT id, expires_at FROM memories").fetchall())
    assert migrated == {
        "web": "2030-01-01T00:00:00.000000Z",
        "web-ui": "2030-01-01T00:00:00.000000Z",
    }
    conn.close()
