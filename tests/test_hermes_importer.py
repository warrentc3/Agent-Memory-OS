from __future__ import annotations

from pathlib import Path

from agent_memory_os import MemoryClient
from agent_memory_os.hermes_importer import import_hermes_memory_files, split_memory_sections


def write_profile_memory(profile_home: Path, *, memory: str, user: str) -> None:
    memories = profile_home / "memories"
    memories.mkdir(parents=True)
    (memories / "MEMORY.md").write_text(memory, encoding="utf-8")
    (memories / "USER.md").write_text(user, encoding="utf-8")


def test_split_memory_sections_uses_hermes_separator() -> None:
    assert split_memory_sections("A\n§\nB\n\n§\nC") == ["A", "B", "C"]


def test_import_hermes_memory_files_is_idempotent_and_acl_scoped(tmp_path):
    profile_home = tmp_path / "profiles" / "neo"
    write_profile_memory(
        profile_home,
        memory="Neo engineering memory.\n§\nHermes service path /tmp/hermes.",
        user="User prefers Traditional Chinese.\n§\nDB mig: rollback-first.",
    )
    client = MemoryClient(home=tmp_path / "amos")

    first = import_hermes_memory_files(client, profile="neo", profile_home=profile_home)
    second = import_hermes_memory_files(client, profile="neo", profile_home=profile_home)

    assert first.as_dict() | {"missing_files": []}
    assert first.scanned == 4
    assert first.inserted == 4
    assert second.scanned == 4
    assert second.inserted == 0
    assert second.updated == 0
    assert second.skipped == 4
    assert client.stats()["total"] == 4

    own_hits = client.search("Traditional Chinese", owner="neo", requester_agent_id="neo")
    assert own_hits
    assert own_hits[0].record.visibility == ["agent:neo"]
    assert own_hits[0].record.source["system"] == "hermes-memory-md-import"
    assert own_hits[0].record.pinned is True

    other_hits = client.search("Traditional Chinese", requester_agent_id="mizuki")
    assert other_hits == []


def test_import_hermes_memory_files_updates_changed_source_slot_without_duplicates(tmp_path):
    profile_home = tmp_path / "profiles" / "neo"
    write_profile_memory(profile_home, memory="Old content", user="User prefers zh-TW.")
    client = MemoryClient(home=tmp_path / "amos")

    first = import_hermes_memory_files(client, profile="neo", profile_home=profile_home)
    assert first.inserted == 2

    (profile_home / "memories" / "MEMORY.md").write_text("New content", encoding="utf-8")
    second = import_hermes_memory_files(client, profile="neo", profile_home=profile_home)

    assert second.updated == 1
    assert second.skipped == 1
    assert client.stats()["total"] == 2
    hits = client.search("New content", owner="neo", requester_agent_id="neo")
    assert hits
    assert hits[0].record.content == "New content"
