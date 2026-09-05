"""Boundaries between runtime tuning, persisted defaults, and UI assets."""

import importlib.util
import sqlite3
from contextlib import closing
from types import ModuleType

import pytest

from agent_memory_os import constants, database_schema, web_ui
from agent_memory_os.migrations.v001_decay_columns import migrate as migrate_v001
from agent_memory_os.migrations.v003_archive_table import migrate as migrate_v003


def _load_fresh(module: ModuleType) -> ModuleType:
    """Evaluate module-level construction without replacing the imported module."""
    assert module.__file__ is not None
    spec = importlib.util.spec_from_file_location(
        f"agent_memory_os._test_{module.__name__.rsplit('.', 1)[-1]}",
        module.__file__,
    )
    assert spec is not None and spec.loader is not None
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)
    return fresh


@pytest.mark.parametrize("runtime_fallback", [30.0, 45.0])
def test_schema_defaults_are_independent_of_runtime_decay_tuning(
    monkeypatch, runtime_fallback
):
    monkeypatch.setattr(constants, "DEFAULT_DECAY_HALF_LIFE_FALLBACK_DAYS", runtime_fallback)
    schema = _load_fresh(database_schema).SCHEMA

    with (
        closing(sqlite3.connect(":memory:")) as fresh,
        closing(sqlite3.connect(":memory:")) as upgraded,
    ):
        fresh.executescript(schema)
        migrate_v003(fresh)
        upgraded.row_factory = sqlite3.Row
        upgraded.execute("CREATE TABLE memories (id TEXT PRIMARY KEY)")
        migrate_v001(upgraded)
        migrate_v003(upgraded)

        for conn in (fresh, upgraded):
            for table in ("memories", "memories_archive"):
                columns = {row[1]: row for row in conn.execute(f"PRAGMA table_info({table})")}
                assert columns["decay_half_life_days"][4] == "30.0"


def test_web_ui_rejects_unresolved_placeholders(monkeypatch):
    monkeypatch.setattr(
        constants, "WEB_UI_TOAST_DURATION_MILLISECONDS", "__AMOS_UNWIRED__"
    )
    with pytest.raises(RuntimeError, match="unresolved template placeholder"):
        _load_fresh(web_ui)
