"""Membership changes must invalidate the client's recall cache immediately.

Regression for a bug found while writing examples/team_memory.py: the client
caches search results per (query, requester, …). Removing an agent from a team
cleared the store's membership cache but NOT the client's result cache, so a
previously-run query kept returning a now-revoked team memory until the cache
evicted it — a security-relevant staleness (revocation didn't take effect).

Assertions check for the SPECIFIC scoped memory's presence/absence rather than
result counts: with a tiny dataset the lexical fallback surfaces every visible
memory as a weak match, so counts are noisy but membership of a given item is exact.
"""

from __future__ import annotations

from agent_memory_os import MemoryClient

TEAM_MEM = "Apollo incident channel is #apollo-oncall."
PROJ_MEM = "Web API key rotates Mondays."


def _texts(client, agent, query):
    return [h.record.content for h in client.search(query, requester_agent_id=agent)]


def _team_setup(tmp_path):
    c = MemoryClient(home=tmp_path)
    for a in ("alice", "bob"):
        c.store.register_agent(a)
    c.create_team("apollo")
    c.add_team_member("apollo", "alice")
    c.add_team_member("apollo", "bob")
    c.add(TEAM_MEM, owner="alice", visibility=["team:apollo"])
    return c


def test_remove_team_member_invalidates_cached_recall(tmp_path):
    """Lineage:
    main: introduced 0e0a0f5f@db-schema-v15.
    """
    c = _team_setup(tmp_path)
    # prime the cache with bob's query WHILE he is a member
    assert TEAM_MEM in _texts(c, "bob", "incident apollo")
    # revoke, then run the SAME query — the revoked team memory must be gone
    c.remove_team_member("apollo", "bob")
    assert TEAM_MEM not in _texts(c, "bob", "incident apollo")


def test_add_team_member_invalidates_cached_recall(tmp_path):
    """Lineage:
    main: introduced 0e0a0f5f@db-schema-v15.
    """
    c = _team_setup(tmp_path)
    c.store.register_agent("carol")
    # prime: carol (not a member) cannot see the team memory
    assert TEAM_MEM not in _texts(c, "carol", "incident apollo")
    # add carol, same query — she should now see it (not the cached miss)
    c.add_team_member("apollo", "carol")
    assert TEAM_MEM in _texts(c, "carol", "incident apollo")


def test_remove_project_member_invalidates_cache_for_nonowner(tmp_path):
    """Lineage:
    main: introduced 0e0a0f5f@db-schema-v15.
    """
    c = _team_setup(tmp_path)  # alice + bob on team apollo
    c.create_project("apollo-web", "apollo")
    c.add_project_member("apollo-web", "alice")
    c.add_project_member("apollo-web", "bob")
    # alice OWNS it; bob is a non-owner project member who can read it
    c.add(PROJ_MEM, owner="alice", visibility=["project:apollo-web"])
    assert PROJ_MEM in _texts(c, "bob", "api key rotates")
    # remove bob from the project — the project memory must leave his recall
    c.remove_project_member("apollo-web", "bob")
    assert PROJ_MEM not in _texts(c, "bob", "api key rotates")
    # ...but alice, the owner, still sees it
    assert PROJ_MEM in _texts(c, "alice", "api key rotates")


def test_other_connection_visibility_revoke_invalidates_cached_recall(tmp_path):
    """Lineage:
    main: introduced bd659853@db-schema-v18.
    """
    writer = MemoryClient(home=tmp_path)
    reader = MemoryClient(home=tmp_path)
    memory = writer.add(
        "Cross-process revocation sentinel.",
        owner="alice",
        visibility=["global"],
    )

    assert memory.id in {
        hit.record.id
        for hit in reader.search("cross process revocation", requester_agent_id="bob")
    }
    writer.update(memory.id, requester_agent_id="alice", visibility=[])

    assert memory.id not in {
        hit.record.id
        for hit in reader.search("cross process revocation", requester_agent_id="bob")
    }
    reader.close()
    writer.close()


def test_other_connection_membership_revoke_invalidates_all_acl_caches(tmp_path):
    """Lineage:
    main: introduced bd659853@db-schema-v18.
    """
    writer = MemoryClient(home=tmp_path)
    reader = MemoryClient(home=tmp_path)
    for agent_id in ("alice", "bob"):
        writer.store.register_agent(agent_id)
    writer.create_team("apollo")
    writer.add_team_member("apollo", "alice")
    writer.add_team_member("apollo", "bob")
    memory = writer.add(
        "Cross-process Apollo membership sentinel.",
        owner="alice",
        visibility=["team:apollo"],
    )

    assert memory.id in {
        hit.record.id
        for hit in reader.search("apollo membership sentinel", requester_agent_id="bob")
    }
    writer.remove_team_member("apollo", "bob")

    assert memory.id not in {
        hit.record.id
        for hit in reader.search("apollo membership sentinel", requester_agent_id="bob")
    }
    reader.close()
    writer.close()
