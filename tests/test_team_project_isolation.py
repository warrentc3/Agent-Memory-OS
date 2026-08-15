"""Team/project memory isolation — the full boundary matrix, as a regression.

Codifies the 2026-07-28 audit: team memories and project memories resolve
through the same ACL hard gate, with projects strictly narrower (membership
comes ONLY from the registry — there is no caller-asserted project id). These
tests pin every boundary an operator relies on so a future change to the ACL
filter, membership cascade, or share helpers cannot silently cross-pollinate
teams or projects.
"""

from __future__ import annotations

import pytest

from agent_memory_os.client import MemoryClient


@pytest.fixture()
def org(tmp_path):
    """Two teams; two sibling projects under T1; one project under T2.

    a1: T1 + P1 · a2: T1 only · a3: T1 + P1b · b1: T2 + P2 · outsider: nothing.
    One memory per scope boundary, plus a private one and a global one.
    """
    client = MemoryClient(home=tmp_path)
    store = client.store
    store.create_team("T1")
    store.create_team("T2")
    store.create_project("P1", team_id="T1")
    store.create_project("P1b", team_id="T1")
    store.create_project("P2", team_id="T2")
    for agent_id, teams in [("a1", ["T1"]), ("a2", ["T1"]), ("a3", ["T1"]),
                            ("b1", ["T2"]), ("outsider", [])]:
        store.register_agent(agent_id, teams=teams)
    store.add_project_member("P1", "a1")
    store.add_project_member("P1b", "a3")
    store.add_project_member("P2", "b1")
    memories = {
        "team T1":    client.add("memo team T1",    owner="a1", visibility=["team:T1"]).id,
        "team T2":    client.add("memo team T2",    owner="b1", visibility=["team:T2"]).id,
        "proj P1":    client.add("memo proj P1",    owner="a1", visibility=["project:P1"]).id,
        "proj P1b":   client.add("memo proj P1b",   owner="a3", visibility=["project:P1b"]).id,
        "proj P2":    client.add("memo proj P2",    owner="b1", visibility=["project:P2"]).id,
        "private a1": client.add("memo private a1", owner="a1", visibility=[]).id,
        "global":     client.add("memo global",     owner="a1", visibility=["global"]).id,
    }
    yield client, memories
    client.close()


# Ownership is part of the expectation: a writer always sees its own memory,
# so a3 (owner of "proj P1b") keeps it even though membership alone would too.
EXPECTED_VIEW = {
    "a1":       {"team T1", "proj P1", "private a1", "global"},
    "a2":       {"team T1", "global"},               # team member, in no project
    "a3":       {"team T1", "proj P1b", "global"},   # sibling project P1 invisible
    "b1":       {"team T2", "proj P2", "global"},
    "outsider": {"global"},
}


def _labels(records):
    return {r.content.replace("memo ", "") for r in records}


@pytest.mark.parametrize("who", sorted(EXPECTED_VIEW))
def test_browse_and_search_show_exactly_the_entitled_set(org, who):
    """Lineage:
    main: introduced b89ea0f8@db-schema-v20.
    """
    client, _ = org
    want = EXPECTED_VIEW[who]
    assert _labels(client.list_recent(requester_agent_id=who, limit=50)) == want
    got = {r.record.content.replace("memo ", "")
           for r in client.search("memo", requester_agent_id=who, limit=50)}
    assert got == want


@pytest.mark.parametrize("who", sorted(EXPECTED_VIEW))
def test_direct_id_probing_matches_the_same_matrix(org, who):
    """get_visible must agree with search — an id in hand grants nothing.

    Lineage:
    main: introduced b89ea0f8@db-schema-v20.
    """
    client, memories = org
    want = EXPECTED_VIEW[who]
    for label, memory_id in memories.items():
        visible = client.get_visible(memory_id, requester_agent_id=who) is not None
        assert visible == (label in want), f"{who} → {label}"


def test_project_membership_requires_team_membership(org):
    """Lineage:
    main: introduced b89ea0f8@db-schema-v20.
    """
    client, _ = org
    with pytest.raises(ValueError):
        client.store.add_project_member("P1", "b1")  # b1 is in T2, not T1


def test_leaving_the_team_revokes_team_and_project_views_of_others(org):
    """The cascade: project membership dies with team membership — but only
    for OTHERS' memories; ownership of one's own writes is never revoked.

    Lineage:
    main: introduced b89ea0f8@db-schema-v20.
    """
    client, memories = org
    store = client.store
    # a4 joins T1+P1b so a3 has a foreign project memory to lose sight of.
    store.register_agent("a4", teams=["T1"])
    store.add_project_member("P1b", "a4")
    foreign = client.add("memo a4 P1b", owner="a4", visibility=["project:P1b"]).id
    assert client.get_visible(foreign, requester_agent_id="a3") is not None

    store.remove_team_member("T1", "a3")

    assert store.projects_for("a3") == []  # cascade removed P1b membership
    assert client.get_visible(foreign, requester_agent_id="a3") is None
    assert client.get_visible(memories["team T1"], requester_agent_id="a3") is None
    # own memory survives (ownership, not membership)
    assert client.get_visible(memories["proj P1b"], requester_agent_id="a3") is not None
    # the remaining member is unaffected
    assert client.get_visible(foreign, requester_agent_id="a4") is not None


def test_caller_asserted_team_id_never_grants_project_memories(org):
    """requester_team_id is SDK-trust-level (the caller already holds admin
    access); it may widen TEAM visibility but must never reach projects —
    project membership resolves exclusively from the registry.

    Lineage:
    main: introduced b89ea0f8@db-schema-v20.
    """
    client, memories = org
    client.store.register_agent("stranger", teams=[])
    assert client.get_visible(memories["team T1"], requester_agent_id="stranger",
                              requester_team_id="T1") is not None
    for label in ("proj P1", "proj P1b"):
        assert client.get_visible(memories[label], requester_agent_id="stranger",
                                  requester_team_id="T1") is None
