import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    # The half-life a memory was configured with (default-for-type, or a value
    # the user set). Feedback tuning scales THIS, so an explicit half-life is
    # no longer clobbered back to the type default on the next retention pass.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(memories)")}
    if "decay_base_half_life_days" not in cols:
        conn.execute("ALTER TABLE memories ADD COLUMN decay_base_half_life_days REAL")
        conn.execute(
            "UPDATE memories SET decay_base_half_life_days = decay_half_life_days "
            "WHERE decay_base_half_life_days IS NULL"
        )
