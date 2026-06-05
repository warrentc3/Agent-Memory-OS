#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from agent_memory_os import MemoryClient

QUERY = "emotional_preference_probe"

FIXTURES = [
    {
        "label": "private_emotional_preference",
        "content": "ACL_LABEL=private_emotional_preference emotional_preference_probe: Mizuki prefers quiet lo-fi recovery rituals after overload.",
        "owner": "mizuki",
        "scope": "agent",
        "type": "preference",
        "visibility": ["agent"],
        "tags": ["emotional_preference_probe", "subjective_qa"],
        "importance": 0.95,
        "confidence": 0.95,
        "source": {"team_id": "bastet", "fixture": "acl_verification", "label": "private_emotional_preference"},
    },
    {
        "label": "team_memory",
        "content": "ACL_LABEL=team_memory emotional_preference_probe: Bastet team may discuss emotional-memory QA boundaries.",
        "owner": "mizuki",
        "scope": "team",
        "type": "note",
        "visibility": ["team:bastet"],
        "tags": ["emotional_preference_probe", "team_memory", "subjective_qa"],
        "importance": 0.75,
        "confidence": 0.9,
        "source": {"team_id": "bastet", "fixture": "acl_verification", "label": "team_memory"},
    },
    {
        "label": "global_memory",
        "content": "ACL_LABEL=global_memory emotional_preference_probe: All agents may know that ACL verification is required.",
        "owner": "mizuki",
        "scope": "global",
        "type": "procedure",
        "visibility": ["global"],
        "tags": ["emotional_preference_probe", "global_memory", "subjective_qa"],
        "importance": 0.55,
        "confidence": 0.9,
        "source": {"team_id": "bastet", "fixture": "acl_verification", "label": "global_memory"},
    },
]

IDENTITIES = {
    "mizuki": {"requester_agent_id": "mizuki", "requester_team_id": "bastet"},
    "neo": {"requester_agent_id": "neo", "requester_team_id": "bastet"},
    "guest": {"requester_agent_id": "guest", "requester_team_id": None},
}

EXPECTED = {
    "mizuki": ["private_emotional_preference", "team_memory", "global_memory"],
    "neo": ["team_memory", "global_memory"],
    "guest": ["global_memory"],
}


def seed(client: MemoryClient) -> None:
    for fixture in FIXTURES:
        payload = {k: v for k, v in fixture.items() if k != "label"}
        client.add(**payload)


def labels_in_text(text: str) -> list[str]:
    return [fixture["label"] for fixture in FIXTURES if fixture["label"] in text]


def verify_identity(client: MemoryClient, identity: str, *, query: str, limit: int, max_tokens: int) -> dict[str, Any]:
    requester = IDENTITIES[identity]
    hits = client.search(query, limit=limit, **requester)
    pack = client.context_pack(query, limit=limit, max_tokens=max_tokens, **requester)
    search_labels = [hit.record.source.get("label") or label_from_content(hit.record.content) for hit in hits]
    pack_labels = labels_in_text(pack)
    expected = EXPECTED[identity]
    return {
        "identity": identity,
        "requester_agent_id": requester["requester_agent_id"],
        "requester_team_id": requester["requester_team_id"],
        "query": query,
        "search_visible_labels": search_labels,
        "context_pack_visible_labels": pack_labels,
        "expected_visible_labels": expected,
        "search_passed": search_labels == expected,
        "context_pack_passed": pack_labels == expected,
        "search_results": [
            {
                "id": hit.record.id,
                "label": label_from_content(hit.record.content),
                "score": round(hit.score, 6),
                "scope": hit.record.scope,
                "type": hit.record.type,
                "owner": hit.record.owner,
                "visibility": hit.record.visibility,
                "content": hit.record.content,
            }
            for hit in hits
        ],
        "context_pack": pack,
    }


def label_from_content(content: str) -> str:
    for fixture in FIXTURES:
        if fixture["label"] in content:
            return fixture["label"]
    return "unknown"


def build_report(home: Path, identities: list[str], *, query: str, limit: int, max_tokens: int, reset: bool) -> dict[str, Any]:
    if reset and home.exists():
        shutil.rmtree(home)
    client = MemoryClient(home=home)
    try:
        seed(client)
        pulls = [verify_identity(client, identity, query=query, limit=limit, max_tokens=max_tokens) for identity in identities]
    finally:
        client.close()
    private_leaks = [
        pull["identity"]
        for pull in pulls
        if pull["identity"] != "mizuki"
        and (
            "private_emotional_preference" in pull["search_visible_labels"]
            or "private_emotional_preference" in pull["context_pack_visible_labels"]
        )
    ]
    return {
        "fixture": "AgentMemoryOS requester-aware ACL subjective QA",
        "home": str(home),
        "pulls": pulls,
        "leak_check": {"passed": not private_leaks, "private_leaked_to": private_leaks},
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed a temporary ACL fixture and pull it as Mizuki, Neo, or Guest.")
    parser.add_argument("--home", default="/tmp/agent-memory-os-acl-verification", help="Temporary AgentMemoryOS home directory.")
    parser.add_argument("--identity", choices=["all", *IDENTITIES.keys()], default="all", help="Identity to pull as.")
    parser.add_argument("--query", default=QUERY)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--max-tokens", type=int, default=600)
    parser.add_argument("--no-reset", action="store_true", help="Do not delete --home before seeding fixtures.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    identities = list(IDENTITIES) if args.identity == "all" else [args.identity]
    report = build_report(
        Path(args.home),
        identities,
        query=args.query,
        limit=args.limit,
        max_tokens=args.max_tokens,
        reset=not args.no_reset,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["leak_check"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
