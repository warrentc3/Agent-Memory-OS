import pytest
import os
import shutil
import tempfile
from pathlib import Path
from agent_memory_os.client import MemoryClient

@pytest.fixture
def temp_memory_home():
    # Create a temporary directory for the memory store to avoid polluting real data
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

@pytest.fixture
def client(temp_memory_home):
    client = MemoryClient(home=temp_memory_home)
    yield client
    client.close()

def test_dco_state_preservation(client):
    """
    Verify State Preservation: Save a complex state -> Offload -> Reload -> Compare.
    """
    session_id = "session_alpha_123"
    complex_state = {
        "goals": ["Optimize DCO performance", "Verify isolation"],
        "hypotheses": {
            "h1": "LruCache is working",
            "h2": "Snapshots are isolated"
        },
        "variables": {
            "counter": 42,
            "status": "active",
            "flags": [True, False, True]
        },
        "metadata": {
            "timestamp": "2026-06-13T10:00:00Z",
            "agent_version": "1.0.0"
        }
    }

    # 1. Offload the complex state
    snapshot_id = client.offload_context(
        snapshot_data=complex_state,
        session_id=session_id,
        trigger="test_verification"
    )

    # 2. Reload the state
    reloaded_state = client.reload_context(session_id=session_id, snapshot_id=snapshot_id)

    # 3. Compare
    assert reloaded_state == complex_state
    assert reloaded_state["goals"][0] == "Optimize DCO performance"
    assert reloaded_state["variables"]["counter"] == 42

def test_dco_session_isolation(client):
    """
    Verify Session Isolation: Ensure session A's snapshot does not leak into session B.
    """
    session_a = "session_A"
    state_a = {"data": "Content for A"}
    
    session_b = "session_B"
    state_b = {"data": "Content for B"}

    # Offload both
    id_a = client.offload_context(state_a, session_a)
    id_b = client.offload_context(state_b, session_b)

    # A specific snapshot id remains bound to its recorded session.
    with pytest.raises(ValueError, match=f"Snapshot {id_a} not found"):
        client.reload_context(session_id=session_b, snapshot_id=id_a)

    # Searching by session must also stay inside the requested session.
    
    reloaded_b = client.reload_context(session_id=session_b)
    assert reloaded_b == state_b
    assert reloaded_b != state_a

    reloaded_a = client.reload_context(session_id=session_a)
    assert reloaded_a == state_a
    assert reloaded_a != state_b

def test_dco_latest_snapshot_retrieval(client):
    """
    Verify Latest Snapshot Retrieval: Verify that calling reload_context without a 
    specific ID retrieves the most recent snapshot for that session.
    """
    session_id = "session_gamma"
    
    state_1 = {"version": 1, "msg": "First snapshot"}
    state_2 = {"version": 2, "msg": "Second snapshot"}
    state_3 = {"version": 3, "msg": "Third (latest) snapshot"}

    # Sequence of offloads
    client.offload_context(state_1, session_id)
    client.offload_context(state_2, session_id)
    client.offload_context(state_3, session_id)

    # Reload without snapshot_id should get the latest
    reloaded = client.reload_context(session_id=session_id)
    
    assert reloaded == state_3
    assert reloaded["version"] == 3
    records = client.store.recent_snapshot_records(session_id, limit=3)
    assert [record.source["snapshot_index"] for record in records] == [2, 1, 0]

def test_dco_nonexistent_session(client):
    """
    Verify that requesting a snapshot for a session with no data raises ValueError.
    """
    with pytest.raises(ValueError, match="No snapshots found for session"):
        client.reload_context(session_id="ghost_session")

def test_dco_nonexistent_snapshot_id(client):
    """
    Verify that requesting a non-existent snapshot ID raises ValueError.
    """
    with pytest.raises(ValueError, match="Snapshot mem_invalid not found"):
        client.reload_context(session_id="any", snapshot_id="mem_invalid")
