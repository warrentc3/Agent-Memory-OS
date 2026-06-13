# Technical Design: Dynamic Context Orchestration (DCO)
## Agent Memory OS - Phase 2

### 1. Overview
Dynamic Context Orchestration (DCO) is designed to manage the movement of agent state and critical context between the "active" working memory (LLM context window) and the "dormant" durable memory (Agent Memory OS). It prevents context overflow while ensuring a seamless transition of operational state during task switching or agent hibernation.

### 2. Core Mechanism
DCO introduces the concept of a `ContextSnapshot`. Instead of just retrieving individual memories, DCO allows the agent to capture a holistic state of its current reasoning, goals, and temporary findings, then offload it to the memory store.

#### 2.1 ContextSnapshot Schema
A `ContextSnapshot` is a specialized memory record that encapsulates the "current state of mind".

- **ID**: `snap_{uuid}`
- **Type**: `snapshot`
- **Content**: A serialized object containing:
  - `active_goals`: List of current objectives.
  - `working_hypotheses`: Current assumptions being tested.
  - `critical_variables`: Key values/IDs the agent is currently tracking.
  - `last_thought_trace`: The final few steps of the reasoning chain.
  - `pending_actions`: Items in the agent's internal queue.
- **Metadata**:
  - `session_id`: Links the snapshot to a specific execution session.
  - `snapshot_index`: Sequence number for versioning.
  - `trigger`: Why the snapshot was taken (e.g., `manual`, `timeout`, `budget_exhausted`, `task_complete`).

### 3. API Definitions (`MemoryClient`)

#### 3.1 `offload_context(snapshot_data: dict, session_id: str, trigger: str = "manual") -> str`
- **Purpose**: Captures the current agent state and stores it as a `ContextSnapshot`.
- **Input**: 
  - `snapshot_data`: Dictionary of state.
  - `session_id`: Unique identifier for the current agent session.
  - `trigger`: The event that triggered the offload.
- **Output**: The `memory_id` of the created snapshot.
- **Logic**:
  1. Serialize `snapshot_data` to JSON.
  2. Create a `MemoryRecord` with `type="snapshot"`.
  3. Store in the `memories` table.
  4. Update the `last_snapshot_id` for the given `session_id` in a separate tracking table (or metadata).

#### 3.2 `reload_context(session_id: str, snapshot_id: str | None = None) -> dict`
- **Purpose**: Retrieves the most recent (or a specific) snapshot to restore agent state.
- **Input**:
  - `session_id`: The session to recover.
  - `snapshot_id`: Optional specific snapshot ID; defaults to the latest.
- **Output**: The deserialized `snapshot_data` dictionary.
- **Logic**:
  1. Locate the requested snapshot ID.
  2. Verify ACL/Visibility.
  3. Deserialize content and return.

### 4. Implementation Plan
1. **Schema Update**: Add `snapshot` to `VALID_MEMORY_TYPES` and implement `ContextSnapshot` helper class.
2. **Client Integration**: Implement `offload_context` and `reload_context` in `MemoryClient`.
3. **State Tracking**: Add a small index or metadata field to efficiently find the "latest" snapshot for a session.
4. **Verification**: Create `test_context_orchestration.py` to verify state preservation across "hibernation" cycles.
