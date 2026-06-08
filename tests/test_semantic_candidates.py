from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import cast

from agent_memory_os import MemoryClient
from agent_memory_os.candidates import Candidate, CandidateProvider


PRIVATE_SECRET = "PRIVATE semantic-only candidate must never leak."


class FakeSemanticProvider:
    name = "fake_semantic"

    def __init__(self, *memory_ids: str, score: float = 0.95):
        self.memory_ids = list(memory_ids)
        self.score = score

    def candidates(self, query: str, **kwargs):
        return [
            Candidate(memory_id=memory_id, provider=self.name, score=self.score, rank=rank)
            for rank, memory_id in enumerate(self.memory_ids, start=1)
        ]


class FailingSemanticProvider:
    name = "failing_semantic"

    def candidates(self, query: str, **kwargs):
        raise RuntimeError("semantic backend unavailable")


class IterationFailingSemanticProvider:
    name = "iteration_failing_semantic"

    def __init__(self, memory_id: str = "missing"):
        self.memory_id = memory_id

    def candidates(self, query: str, **kwargs):
        yield Candidate(memory_id=self.memory_id, provider=self.name, score=0.9)
        raise RuntimeError("semantic backend failed while streaming")


class HostileNameSemanticProvider:
    @property
    def name(self):
        raise RuntimeError("provider name unavailable")

    def candidates(self, query: str, **kwargs):
        raise RuntimeError("semantic backend unavailable")


class DuplicateFloodSemanticProvider:
    name = "duplicate_flood_semantic"

    def __init__(self, memory_id: str):
        self.memory_id = memory_id
        self.iterations = 0

    def candidates(self, query: str, **kwargs):
        for _ in range(50_000):
            self.iterations += 1
            yield Candidate(memory_id=self.memory_id, provider=self.name, score=0.1)


class MalformedSemanticProvider:
    name = "malformed_semantic"

    def __init__(self, valid_memory_id: str):
        self.valid_memory_id = valid_memory_id

    def candidates(self, query: str, **kwargs):
        return [
            object(),
            Candidate(memory_id="", provider=self.name, score=0.9),
            Candidate(memory_id="   ", provider=self.name, score=0.9),
            Candidate(memory_id=self.valid_memory_id, provider=self.name, score=float("nan")),
            Candidate(memory_id=self.valid_memory_id, provider=self.name, score="not-a-number"),  # type: ignore[arg-type]
            Candidate(memory_id=self.valid_memory_id, provider=self.name, score=0.85),
        ]


class ExcessiveSemanticProvider:
    name = "excessive_semantic"

    def candidates(self, query: str, **kwargs):
        return [Candidate(memory_id=f"missing-{idx}", provider=self.name, score=0.1) for idx in range(50_000)]


def _past_iso(days: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _set_candidate_providers(client: MemoryClient, *providers: object) -> None:
    client.store.candidate_providers = [cast(CandidateProvider, provider) for provider in providers]


def test_semantic_candidate_is_rejoined_from_sqlite(tmp_path):
    client = MemoryClient(home=tmp_path)
    record = client.add(
        "SQLite authoritative content returned after semantic candidate rejoin.",
        owner="neo",
        visibility=["global"],
        tags=["semantic"],
    )
    _set_candidate_providers(client, FakeSemanticProvider(record.id))

    hits = client.search("unrelated paraphrase with no lexical overlap", requester_agent_id="mizuki")

    assert [hit.record.id for hit in hits] == [record.id]
    assert hits[0].record.content == "SQLite authoritative content returned after semantic candidate rejoin."
    assert hits[0].reason.startswith("semantic:fake_semantic")


def test_semantic_candidate_private_memory_does_not_leak_to_other_agent(tmp_path):
    client = MemoryClient(home=tmp_path)
    private = client.add(
        PRIVATE_SECRET,
        owner="neo",
        visibility=["agent"],
        tags=["semantic", "private"],
        importance=1.0,
    )
    public = client.add(
        "Public semantic candidate is allowed.",
        owner="neo",
        visibility=["global"],
        tags=["semantic"],
    )
    _set_candidate_providers(client, FakeSemanticProvider(private.id, public.id))

    hits = client.search("semantic-only recall", requester_agent_id="mizuki")

    contents = [hit.record.content for hit in hits]
    assert PRIVATE_SECRET not in contents
    assert "Public semantic candidate is allowed." in contents
    assert private.id not in [hit.record.id for hit in hits]


def test_semantic_candidate_expired_memory_is_excluded(tmp_path):
    client = MemoryClient(home=tmp_path)
    expired = client.add(
        "Expired semantic candidate must be filtered.",
        owner="neo",
        visibility=["global"],
        tags=["semantic"],
        expires_at=_past_iso(),
    )
    current = client.add(
        "Current semantic candidate remains visible.",
        owner="neo",
        visibility=["global"],
        tags=["semantic"],
    )
    _set_candidate_providers(client, FakeSemanticProvider(expired.id, current.id))

    hits = client.search("semantic-only recall", requester_agent_id="mizuki")

    contents = [hit.record.content for hit in hits]
    assert "Expired semantic candidate must be filtered." not in contents
    assert "Current semantic candidate remains visible." in contents


def test_semantic_candidate_duplicate_is_deduped_by_memory_id(tmp_path):
    client = MemoryClient(home=tmp_path)
    record = client.add(
        "Duplicate semantic candidate should appear once.",
        owner="neo",
        visibility=["global"],
        tags=["duplicate"],
    )
    _set_candidate_providers(client, FakeSemanticProvider(record.id, record.id))

    hits = client.search("Duplicate semantic candidate", requester_agent_id="mizuki")

    assert [hit.record.id for hit in hits].count(record.id) == 1


def test_semantic_provider_failure_degrades_to_fts_and_fallback(tmp_path):
    client = MemoryClient(home=tmp_path)
    safe = client.add(
        "FTS fallback remains available when semantic backend fails.",
        owner="neo",
        visibility=["global"],
        tags=["fallback"],
    )
    _set_candidate_providers(client, FailingSemanticProvider())

    hits = client.search("FTS fallback", requester_agent_id="mizuki")

    assert [hit.record.id for hit in hits] == [safe.id]
    assert hits[0].reason.startswith("fts")


def test_semantic_provider_iteration_failure_degrades_to_fts(tmp_path):
    client = MemoryClient(home=tmp_path)
    safe = client.add(
        "FTS remains available when semantic provider stream fails.",
        owner="neo",
        visibility=["global"],
        tags=["stream"],
    )
    _set_candidate_providers(client, IterationFailingSemanticProvider())

    hits = client.search("provider stream", requester_agent_id="mizuki")

    assert [hit.record.id for hit in hits] == [safe.id]
    assert hits[0].reason.startswith("fts")


def test_semantic_provider_iteration_failure_discards_partial_valid_candidates(tmp_path):
    client = MemoryClient(home=tmp_path)
    semantic = client.add(
        "Partial semantic result must be discarded when provider stream fails.",
        owner="neo",
        visibility=["global"],
        tags=["semantic"],
    )
    safe = client.add(
        "FTS remains authoritative after partial semantic stream failure.",
        owner="neo",
        visibility=["global"],
        tags=["authoritative"],
    )
    _set_candidate_providers(client, IterationFailingSemanticProvider(semantic.id))

    hits = client.search("authoritative", requester_agent_id="mizuki")

    assert [hit.record.id for hit in hits] == [safe.id]
    assert semantic.id not in [hit.record.id for hit in hits]


def test_hostile_provider_name_failure_degrades_to_fts(tmp_path):
    client = MemoryClient(home=tmp_path)
    safe = client.add(
        "FTS survives hostile semantic provider name property.",
        owner="neo",
        visibility=["global"],
        tags=["hostile"],
    )
    _set_candidate_providers(client, HostileNameSemanticProvider())

    hits = client.search("hostile provider", requester_agent_id="mizuki")

    assert [hit.record.id for hit in hits] == [safe.id]
    assert hits[0].reason.startswith("fts")


def test_duplicate_flood_semantic_candidates_are_raw_capped(tmp_path):
    client = MemoryClient(home=tmp_path)
    safe = client.add(
        "Duplicate flood semantic candidate is capped.",
        owner="neo",
        visibility=["global"],
        tags=["semantic"],
    )
    provider = DuplicateFloodSemanticProvider(safe.id)
    _set_candidate_providers(client, provider)

    hits = client.search("semantic-only recall", requester_agent_id="mizuki")

    assert [hit.record.id for hit in hits] == [safe.id]
    assert provider.iterations <= 500


def test_malformed_semantic_candidates_are_skipped_without_breaking_valid_candidate(tmp_path):
    client = MemoryClient(home=tmp_path)
    valid = client.add(
        "Valid semantic candidate survives malformed sidecar output.",
        owner="neo",
        visibility=["global"],
        tags=["semantic"],
    )
    _set_candidate_providers(client, MalformedSemanticProvider(valid.id))

    hits = client.search("semantic-only recall", requester_agent_id="mizuki")

    assert [hit.record.id for hit in hits] == [valid.id]
    assert hits[0].reason.startswith("semantic:malformed_semantic")


def test_excessive_semantic_candidates_are_capped_and_do_not_break_fts(tmp_path):
    client = MemoryClient(home=tmp_path)
    safe = client.add(
        "FTS survives excessive semantic sidecar candidates.",
        owner="neo",
        visibility=["global"],
        tags=["excessive"],
    )
    _set_candidate_providers(client, ExcessiveSemanticProvider())

    hits = client.search("excessive semantic sidecar", requester_agent_id="mizuki")

    assert [hit.record.id for hit in hits] == [safe.id]
    assert hits[0].reason.startswith("fts")


def test_context_pack_report_does_not_include_unauthorized_semantic_candidates(tmp_path):
    client = MemoryClient(home=tmp_path)
    private = client.add(
        PRIVATE_SECRET,
        owner="neo",
        visibility=["agent"],
        tags=["semantic"],
        importance=1.0,
    )
    public = client.add(
        "Authorized semantic candidate can enter context.",
        owner="neo",
        visibility=["global"],
        tags=["semantic"],
    )
    _set_candidate_providers(client, FakeSemanticProvider(private.id, public.id))

    report = client.context_pack_report(
        "semantic-only recall",
        requester_agent_id="mizuki",
        max_tokens=160,
    )

    assert PRIVATE_SECRET not in report.text
    assert "Authorized semantic candidate can enter context." in report.text
    assert private.id not in [decision.memory_id for decision in report.decisions]


def test_orphan_semantic_candidate_is_ignored(tmp_path):
    client = MemoryClient(home=tmp_path)
    public = client.add(
        "Only real SQLite rows can be returned.",
        owner="neo",
        visibility=["global"],
        tags=["semantic"],
    )
    _set_candidate_providers(client, FakeSemanticProvider("missing-memory-id", public.id))

    hits = client.search("semantic-only recall", requester_agent_id="mizuki")

    assert [hit.record.id for hit in hits] == [public.id]
