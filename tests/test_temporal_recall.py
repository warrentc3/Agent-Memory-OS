"""Time-range recall and temporal context.

Every record carried timestamps, but they only ever tilted *ranking* through
the freshness factor — which can reorder what a query already matched and can
never answer "what did I learn that week". These cover the two halves of
closing that gap: selecting by a time window, and recovering the memories that
were recorded around a moment.
"""

import datetime as dt

import pytest

from agent_memory_os import MemoryClient

BASE = dt.datetime(2026, 7, 25, 14, 0, tzinfo=dt.timezone.utc)


def _at(client, content, *, owner="alice", visibility=("global",), offset=0,
        field="created_at"):
    """Add a memory and back-date it, so tests read like a real timeline."""
    record = client.add(content, owner=owner, visibility=list(visibility))
    stamp = (BASE + dt.timedelta(seconds=offset)).isoformat(timespec="seconds")
    client.store.conn.execute(
        f"UPDATE memories SET {field} = ? WHERE id = ?", (stamp, record.id)
    )
    client.store.conn.commit()
    client.cache.clear()
    return record


def _fixture(tmp_path):
    client = MemoryClient(home=tmp_path)
    for agent in ("alice", "carol"):
        client.store.register_agent(agent, kind="hermes")
    return client


def test_search_can_select_a_time_window(tmp_path):
    client = _fixture(tmp_path)
    _at(client, "incident start zebra", offset=0)
    _at(client, "nvidia fails zebra", offset=120)
    _at(client, "weeks later zebra", offset=86400 * 20)
    _at(client, "long before zebra", offset=-86400 * 30)

    everything = client.search("zebra", requester_agent_id="alice", limit=20)
    assert len(everything) == 4

    that_day = client.search(
        "zebra", requester_agent_id="alice", limit=20,
        since="2026-07-25T00:00:00+00:00", until="2026-07-26T00:00:00+00:00",
    )
    assert {r.record.content for r in that_day} == {
        "incident start zebra", "nvidia fails zebra"
    }


def test_window_is_half_open_so_adjacent_windows_tile(tmp_path):
    """[since, until) — a record exactly on the boundary belongs to exactly one
    of two adjacent windows, never both."""
    client = _fixture(tmp_path)
    edge = _at(client, "boundary zebra", offset=0)
    boundary = BASE.isoformat(timespec="seconds")
    later = (BASE + dt.timedelta(hours=1)).isoformat(timespec="seconds")
    earlier = (BASE - dt.timedelta(hours=1)).isoformat(timespec="seconds")

    after = client.search("zebra", requester_agent_id="alice", since=boundary, until=later)
    before = client.search("zebra", requester_agent_id="alice", since=earlier, until=boundary)
    assert [r.record.id for r in after] == [edge.id]   # `since` is inclusive
    assert before == []                                # `until` is exclusive


def test_window_composes_with_the_acl_rather_than_replacing_it(tmp_path):
    """A time filter must narrow an already-gated candidate set. If it were
    applied instead of the ACL, asking for a window would leak."""
    client = _fixture(tmp_path)
    _at(client, "alice private zebra", visibility=(), offset=60)
    _at(client, "shared zebra", visibility=("global",), offset=60)

    carol = client.search(
        "zebra", requester_agent_id="carol",
        since="2026-07-25T00:00:00+00:00", until="2026-07-26T00:00:00+00:00",
    )
    assert {r.record.content for r in carol} == {"shared zebra"}


def test_window_applies_to_every_retrieval_track(tmp_path):
    """search() fans out into FTS, authority, link expansion, semantic rejoin
    and a fallback. A track missing the filter would return out-of-window rows,
    so this pins an authority (bedrock) record, which reaches results through a
    query-independent path that ignores the search text entirely."""
    client = _fixture(tmp_path)
    bedrock = client.add(
        "bedrock constant", owner="alice", visibility=["global"],
        source={"permanence": 1, "weight": 10},
    )
    client.store.conn.execute(
        "UPDATE memories SET created_at = ? WHERE id = ?",
        ((BASE + dt.timedelta(days=40)).isoformat(timespec="seconds"), bedrock.id),
    )
    client.store.conn.commit()
    client.cache.clear()
    _at(client, "in window zebra", offset=0)

    hits = client.search(
        "zebra", requester_agent_id="alice", limit=20,
        since="2026-07-25T00:00:00+00:00", until="2026-07-26T00:00:00+00:00",
    )
    assert bedrock.id not in {r.record.id for r in hits}, (
        "an out-of-window bedrock record reached results through the authority track"
    )


def test_time_field_selects_which_clock(tmp_path):
    """created_at ("when did I learn this") and updated_at ("when did it last
    change") are different questions; a record revised long after it was formed
    must answer each correctly."""
    client = _fixture(tmp_path)
    record = _at(client, "revised zebra", offset=0)
    client.store.conn.execute(
        "UPDATE memories SET updated_at = ? WHERE id = ?",
        ((BASE + dt.timedelta(days=30)).isoformat(timespec="seconds"), record.id),
    )
    client.store.conn.commit()
    client.cache.clear()
    window = {"since": "2026-07-25T00:00:00+00:00", "until": "2026-07-26T00:00:00+00:00"}

    assert client.search("zebra", requester_agent_id="alice", **window)
    assert not client.search(
        "zebra", requester_agent_id="alice", time_field="updated_at", **window
    )


def test_unknown_time_field_is_rejected(tmp_path):
    client = _fixture(tmp_path)
    with pytest.raises(ValueError, match="time field must be one of"):
        client.search("zebra", requester_agent_id="alice", time_field="content")


# ---------- temporal context ----------


def test_timeline_recovers_what_was_recorded_around_a_memory(tmp_path):
    """Links record associations someone asserted; a timeline surfaces the ones
    that simply happened together, which is context no explicit link holds."""
    client = _fixture(tmp_path)
    anchor = _at(client, "incident start", offset=0)
    _at(client, "nvidia fails", offset=120)
    _at(client, "reboot approved", offset=900)
    _at(client, "unrelated weeks later", offset=86400 * 20)

    near = client.timeline(anchor_id=anchor.id, window_seconds=1800,
                           requester_agent_id="alice")
    assert [e["record"].content for e in near] == [
        "nvidia fails", "reboot approved",
    ]
    assert [e["offset_seconds"] for e in near] == [120.0, 900.0]
    assert anchor.id not in {e["record"].id for e in near}, "anchor returned itself"


def test_timeline_offsets_are_signed_so_before_and_after_are_distinguishable(tmp_path):
    client = _fixture(tmp_path)
    anchor = _at(client, "anchor", offset=0)
    _at(client, "half an hour earlier", offset=-1800)
    _at(client, "ten minutes later", offset=600)

    by_content = {
        e["record"].content: e["offset_seconds"]
        for e in client.timeline(anchor_id=anchor.id, window_seconds=3600,
                                 requester_agent_id="alice")
    }
    assert by_content["half an hour earlier"] == -1800.0
    assert by_content["ten minutes later"] == 600.0


def test_timeline_is_acl_gated_on_both_the_anchor_and_the_neighbours(tmp_path):
    """An invisible anchor must not be usable as a probe, and a neighbour the
    requester cannot see must not appear just because it is near in time."""
    client = _fixture(tmp_path)
    private_anchor = _at(client, "alice private anchor", visibility=(), offset=0)
    _at(client, "alice private neighbour", visibility=(), offset=60)
    _at(client, "shared neighbour", visibility=("global",), offset=60)

    # carol cannot see the anchor: indistinguishable from "no such memory"
    assert client.timeline(anchor_id=private_anchor.id, window_seconds=1800,
                           requester_agent_id="carol") == []

    # and anchoring on a bare timestamp still gates the neighbours
    seen = client.timeline(around=BASE.isoformat(timespec="seconds"),
                           window_seconds=1800, requester_agent_id="carol")
    assert [e["record"].content for e in seen] == ["shared neighbour"]


def test_timeline_requires_an_anchor_and_a_positive_window(tmp_path):
    client = _fixture(tmp_path)
    with pytest.raises(ValueError, match="requires around="):
        client.timeline(requester_agent_id="alice")
    with pytest.raises(ValueError, match="window_seconds must be positive"):
        client.timeline(around=BASE.isoformat(), window_seconds=0,
                        requester_agent_id="alice")


def test_windowed_and_unwindowed_searches_do_not_share_a_cache_entry(tmp_path):
    """The window is part of a recall's identity: without it in the cache key,
    the second call would be served the first call's results."""
    client = _fixture(tmp_path)
    _at(client, "in window zebra", offset=0)
    _at(client, "far later zebra", offset=86400 * 20)

    unwindowed = client.search("zebra", requester_agent_id="alice", limit=20)
    windowed = client.search(
        "zebra", requester_agent_id="alice", limit=20,
        since="2026-07-25T00:00:00+00:00", until="2026-07-26T00:00:00+00:00",
    )
    assert len(unwindowed) == 2
    assert len(windowed) == 1


# ---------- time-bound parsing ----------


def test_relative_ages_and_absolute_instants_both_resolve():
    """An operator asking what they learned last week types `7d`, not an ISO
    instant; an automated caller passes the instant. Both must land on the same
    comparable form."""
    from agent_memory_os.schema import resolve_time_bound

    now = dt.datetime(2026, 9, 17, 12, 0, tzinfo=dt.timezone.utc)
    assert resolve_time_bound("7d", now=now) == "2026-09-10T12:00:00+00:00"
    assert resolve_time_bound("36h", now=now) == "2026-09-16T00:00:00+00:00"
    assert resolve_time_bound("2w", now=now) == "2026-09-03T12:00:00+00:00"
    assert resolve_time_bound("2026-07-25") == "2026-07-25T00:00:00+00:00"
    assert resolve_time_bound("2026-07-25T14:00:00Z") == "2026-07-25T14:00:00+00:00"
    # an offset names an instant, so it must convert rather than compare as text
    assert resolve_time_bound("2026-07-25T14:00:00+08:00") == "2026-07-25T06:00:00+00:00"
    # absent stays absent, so callers can forward an unset flag untouched
    assert resolve_time_bound(None) is None
    assert resolve_time_bound("  ") is None


def test_unparseable_time_bound_is_rejected_not_guessed():
    from agent_memory_os.schema import resolve_time_bound

    with pytest.raises(ValueError, match="ISO-8601 instant or a relative age"):
        resolve_time_bound("last tuesday")


def test_mcp_exposes_the_window_and_the_timeline(tmp_path, monkeypatch):
    """The MCP tools are how the agents actually reach this, so the params have
    to survive tool registration — a schema mismatch fails only at call time."""
    from agent_memory_os import mcp_server

    monkeypatch.setenv("AGENT_MEMORY_HOME", str(tmp_path))
    server = mcp_server.create_server()
    tools = {t.name: t for t in _tools(server)}
    assert "memory_timeline" in tools
    schema = getattr(tools["memory_search"], "inputSchema", None) or getattr(
        tools["memory_search"], "parameters", {}
    )
    assert {"since", "until"} <= set(schema.get("properties", {}))


def _tools(server):
    import asyncio

    manager = getattr(server, "_tool_manager", None)
    if manager is not None:
        return list(manager.list_tools())
    return asyncio.run(server.list_tools())


def test_web_api_exposes_the_window_and_the_timeline(tmp_path):
    from fastapi.testclient import TestClient

    from agent_memory_os.web_app import create_app

    client = _fixture(tmp_path)
    _at(client, "incident zebra", offset=0)
    _at(client, "nvidia zebra", offset=120)
    _at(client, "much later zebra", offset=86400 * 20)
    client.close()

    web = TestClient(create_app(home=tmp_path, token=None))
    common = {"q": "zebra", "requester_agent_id": "alice"}
    assert len(web.get("/api/search", params=common).json()["results"]) == 3
    windowed = web.get("/api/search", params={
        **common, "since": "2026-07-25", "until": "2026-07-26"}).json()["results"]
    assert len(windowed) == 2

    entries = web.get("/api/timeline", params={
        "around": "2026-07-25T14:00:00Z", "window_minutes": 30,
        "requester_agent_id": "alice"}).json()["entries"]
    assert [e["memory"]["content"] for e in entries] == ["incident zebra", "nvidia zebra"]
    assert [e["offset_seconds"] for e in entries] == [0.0, 120.0]


def test_web_api_rejects_a_bad_time_bound_with_400_not_500(tmp_path):
    """Malformed operator input must fail cleanly — a 500 here would show up as
    a broken console rather than a correctable mistake."""
    from fastapi.testclient import TestClient

    from agent_memory_os.web_app import create_app

    response = TestClient(create_app(home=tmp_path, token=None)).get(
        "/api/search", params={"q": "zebra", "since": "last tuesday"}
    )
    assert response.status_code == 400
    assert "relative age" in response.json()["detail"]
