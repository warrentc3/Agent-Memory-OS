import pytest

from agent_memory_os import MemoryClient
from agent_memory_os.web_ui import PAGE

FLEET_TOML = """
[agents.cc-main]
display_name = "Claude Code"
kind = "claude-code"
teams = ["apollo", "shared-infra"]

[agents.hermes-neo]
kind = "hermes"
teams = ["apollo", "ops"]

[agents.hermes-mizuki]
kind = "hermes"
teams = ["apollo"]
"""


def test_agents_toml_declares_the_fleet_on_open(tmp_path):
    """Lineage:
    main: introduced 94742013@db-schema-v8.
    """
    (tmp_path / "agents.toml").write_text(FLEET_TOML)

    client = MemoryClient(home=tmp_path)

    assert sorted(client.configured_agents) == ["cc-main", "hermes-mizuki", "hermes-neo"]
    neo = client.store.get_agent("hermes-neo")
    assert neo["kind"] == "hermes" and neo["teams"] == ["apollo", "ops"]

    # config-declared teams drive ACL immediately: multi-team, multi-project
    client.add("Apollo shared plan.", owner="cc-main", visibility=["team:apollo"])
    client.add("Ops runbook.", owner="hermes-neo", visibility=["team:ops"])
    assert client.search("apollo plan", requester_agent_id="hermes-mizuki") != []
    neo_hits = {h.record.content for h in client.search("ops runbook", requester_agent_id="hermes-neo")}
    assert "Ops runbook." in neo_hits
    mizuki_hits = {h.record.content for h in client.search("ops runbook", requester_agent_id="hermes-mizuki")}
    assert "Ops runbook." not in mizuki_hits  # not an ops member


def test_agents_toml_is_authoritative_for_listed_agents(tmp_path):
    """Lineage:
    main: introduced 94742013@db-schema-v8.
    """
    (tmp_path / "agents.toml").write_text(FLEET_TOML)
    client = MemoryClient(home=tmp_path)
    # manual drift on a file-managed agent...
    client.register_agent("hermes-neo", kind="hermes", teams=["rogue"])
    # unmanaged manual agent stays untouched
    client.register_agent("manual-one", kind="custom", teams=["zeta"])
    client.close()

    reopened = MemoryClient(home=tmp_path)  # file re-applied

    assert reopened.store.get_agent("hermes-neo")["teams"] == ["apollo", "ops"]
    assert reopened.store.get_agent("manual-one")["teams"] == ["zeta"]


def test_agents_toml_errors_fail_fast_with_context(tmp_path):
    """Lineage:
    main: introduced 94742013@db-schema-v8.
    """
    (tmp_path / "agents.toml").write_text("[agents.bad]\nkind = \"wizard\"\n")
    with pytest.raises(ValueError, match="agents.toml.*bad.*kind"):
        MemoryClient(home=tmp_path)

    (tmp_path / "agents.toml").write_text("not [ valid toml")
    with pytest.raises(ValueError, match="invalid"):
        MemoryClient(home=tmp_path)


def test_missing_config_is_fine(tmp_path):
    """Lineage:
    main: introduced 94742013@db-schema-v8.
    """
    client = MemoryClient(home=tmp_path)
    assert client.configured_agents == []


def test_web_ui_ships_five_locales():
    """Lineage:
    main: introduced 94742013@db-schema-v8.
    """
    for locale in ('"zh-TW"', '"zh-CN"', '"ja"', '"ko"', '"en"'):
        assert locale in PAGE
    assert "locale-pick" in PAGE
    assert "儀表板" in PAGE and "仪表板" in PAGE
    assert "ダッシュボード" in PAGE and "대시보드" in PAGE
    assert "applyLocale" in PAGE
