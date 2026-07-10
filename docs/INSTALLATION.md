# Installation and Deployment Guide: Agent Memory OS v0.4

This guide provides detailed instructions for installing and deploying Agent Memory OS v0.4.

## 📋 System Requirements
- **Operating System:** Linux, macOS, or Windows (WSL2 recommended).
- **Python Version:** Python 3.11 or higher.
- **Hardware:** Minimum 4GB RAM (Recommended 8GB+ for large memory graphs).

## 🛠 Installation Steps

### 1. Clone the Repository
```bash
git clone git@gitlab.com:hermes-agent-bastet/agent-memory-os.git
cd agent-memory-os
```

### 2. Set Up Virtual Environment
It is highly recommended to use a virtual environment to avoid dependency conflicts.
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install the Package
Install the core package and its optional dependencies for MCP and API support:
```bash
pip install .[mcp,api,dev]
```
*For developers who intend to modify the source code, use editable mode:*
```bash
pip install -e .[mcp,api,dev]
```

## ⚙️ Configuration

### Environment Variables
The system relies on the `AGENT_MEMORY_HOME` environment variable to determine where memory stores and configuration files are located.

**Linux/macOS:**
```bash
export AGENT_MEMORY_HOME="~/agent_memory_data"
```

**Windows (PowerShell):**
```powershell
$env:AGENT_MEMORY_HOME = "$HOME\agent_memory_data"
```

### Initializing the Memory Store
Run the initialization command to set up the local SQLite/Graph database structure:
```bash
agent-memory init
```

## 🚀 Usage Example

### Running the CLI Tool
You can interact with the memory system directly via the `agent-memory` CLI.

**Add a memory:**
```bash
agent-memory add "The capital of France is Paris."
```

**Retrieve a memory (Resonance Recall):**
```bash
agent-memory recall "Where is Paris?"
```

**Check System Status:**
```bash
agent-memory status
```

## 🚢 Deployment Notes
For production deployment, it is recommended to run Agent Memory OS as a background service using `systemd` or within a Docker container. Ensure that the `AGENT_MEMORY_HOME` directory is mounted on a persistent volume to avoid data loss.
