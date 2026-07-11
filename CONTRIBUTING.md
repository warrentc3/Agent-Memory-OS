# Contributing to AgentMemoryOS

Thanks for helping! This is a local-first memory engine for AI-agent teams, and
contributions of all sizes are welcome.

## Getting set up

```bash
git clone https://github.com/yamantaka520/Agent-Memory-OS
cd Agent-Memory-OS
pip install -e ".[dev,api,semantic]"   # editable install + test/web/vector extras
pytest                                  # the full suite should pass before you start
agent-memory doctor                     # confirms FTS5 + optional backends
```

Requires Python 3.11+. CI runs the suite on Ubuntu, macOS, and Windows across
Python 3.11–3.13, plus an upgrade-path job that proves a database written by the
last released version migrates forward.

## Ground rules (the invariants that keep this project correct)

Please preserve these — they are the heart of the design (see [SPEC.md](SPEC.md)):

- **SQLite is the single source of truth.** FTS/vector/resonance indexes are
  disposable and rebuildable; candidate providers return ids only, and every
  candidate rejoins SQLite behind the **ACL and expiry hard gates** before its
  content is used. Never let a candidate path leak content around the gate.
- **Visibility is a hard gate, not a score.** Private/agent/team/project/global
  ACL is enforced before ranking. If you touch a read path, add a test proving an
  unauthorized requester cannot see the memory.
- **Schema changes go through a forward-only migration** (`db.py` migrations +
  bump the version) and must upgrade cleanly from the previous release.
- **Web console parity**: an engine feature that changes what users can inspect or
  control should ship with matching Web UI support. New user-facing console
  strings must be added to all locale dicts (`web_ui.py`) — English is the key/fallback.
- **Federation/ACL merges stay trust-gated** (see [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md)).

## Making a change

1. Branch off `main`.
2. Add or update tests (`tests/`). Bug fixes should include a regression test that
   fails before your fix.
3. Run `pytest` locally; keep it green.
4. Keep the change focused; match the surrounding code's style (no reformatting
   churn). Update docs/CHANGELOG (`[Unreleased]`) when behavior changes.
5. Open a PR against `main` with a clear description of the what and why.

## Sign your commits (DCO)

We use the [Developer Certificate of Origin](https://developercertificate.org/).
Certify that you wrote (or have the right to submit) the change by signing off:

```bash
git commit -s -m "your message"      # adds a Signed-off-by line
```

## Compatibility

From 1.0 we follow SemVer for the public surfaces listed in
[COMPATIBILITY.md](COMPATIBILITY.md) (SDK API, CLI, HTTP API, schema, bundle
format). Breaking one of those is a MAJOR change — flag it in your PR.

## Security

Please do **not** file public issues for vulnerabilities — see [SECURITY.md](SECURITY.md)
for private reporting.

## Releases

Releases are cut by maintainers (bump → CHANGELOG → tag → PyPI/Docker via CI).
You don't need to touch versioning in a PR; just add a CHANGELOG `[Unreleased]` note.

By contributing, you agree your contributions are licensed under the project's
[Apache-2.0](LICENSE) license.
