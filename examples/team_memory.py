#!/usr/bin/env python3
"""Team memory in ~40 lines: three agents, one shared brain, a hard ACL.

Scenario — a team "apollo" with a web sub-project:
  • alice, bob  → members of team apollo
  • alice       → also on project apollo-web (a subset of the team)
  • carol       → an outsider (no membership)

We write memories at four visibility levels and show that each agent recalls
exactly — and only — what its membership entitles it to. No LLM, no server:
one temporary SQLite file.

Run it:  python examples/team_memory.py
"""

from __future__ import annotations

import tempfile

from agent_memory_os import MemoryClient


def recall(client: MemoryClient, agent: str, query: str) -> list[str]:
    """What `agent` can actually retrieve — the ACL runs before ranking."""
    return [h.record.content for h in client.search(query, requester_agent_id=agent)]


def main() -> None:
    client = MemoryClient(home=tempfile.mkdtemp(prefix="amos-example-"))

    # --- set up the org: a team, a sub-project, and their members ---
    for agent in ("alice", "bob", "carol"):
        client.register_agent(agent)
    client.create_team("apollo", name="Apollo")
    client.add_team_member("apollo", "alice")
    client.add_team_member("apollo", "bob")
    client.create_project("apollo-web", "apollo", name="Apollo Web")
    client.add_project_member("apollo-web", "alice")  # bob is NOT on the project

    # --- alice writes memories at four visibility levels ---
    client.add("Deploy target is port 8000.", owner="alice", visibility=["global"])
    client.add("Apollo's incident channel is #apollo-oncall.",
               owner="alice", visibility=["team:apollo"])
    client.add("Web project API key rotates every Monday.",
               owner="alice", visibility=["project:apollo-web"])
    client.add("Alice's personal scratch note.", owner="alice", visibility=[])

    # --- who sees what? ---
    print("Query: recall everything each agent can see\n")
    for agent in ("alice", "bob", "carol"):
        seen = recall(client, agent, "deploy incident api key note port apollo")
        print(f"  {agent:6}sees {len(seen)}:")
        for c in seen:
            print(f"           - {c}")
        print()

    # Expected, and worth asserting so the example doubles as a smoke test:
    assert len(recall(client, "alice", "deploy incident api key note")) == 4  # all incl. private
    bob_seen = recall(client, "bob", "deploy incident api key note")
    assert len(bob_seen) == 2                                                  # global + team only
    assert all("project" not in s.lower() and "personal" not in s.lower() for s in bob_seen)
    assert len(recall(client, "carol", "deploy incident api key note")) == 1   # global only

    # --- a prompt-ready, token-budgeted context pack for bob ---
    pack = client.context_pack("what do I need to know about apollo deploys?",
                               requester_agent_id="bob", max_tokens=400)
    print("Context pack for bob (ACL-filtered, budgeted):\n")
    print("  " + pack.replace("\n", "\n  "))

    # --- revocation re-scopes recall instantly ---
    client.remove_team_member("apollo", "bob")
    after = recall(client, "bob", "deploy incident api key note")
    assert not any("incident" in s for s in after)   # the team memory is gone for bob
    assert any("port 8000" in s for s in after)       # global memory still reaches bob
    print("\nAfter removing bob from apollo: the team memory is no longer recallable "
          f"by bob (he now sees only {len(after)} global memory). ✓")
    print("\nEverything above ran against one local SQLite file — no LLM, no server.")


if __name__ == "__main__":
    main()
