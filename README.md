# freeagent-ai

Generic mechanics and concepts for AI agents working with a FreeAgent account through the API.
Nothing here is specific to one business: no contact, project or bank-account IDs, no rates, no client rules.
The business keeps those wherever it likes (see "Business-specific configuration").

## Contents

| Path | What |
|------|------|
| `freeagent_ai/` | Python client: credentials file, 401 auto-refresh, `login`, `status` |
| `docs/auth.md` | OAuth setup, credentials file, refresh, re-login |
| `docs/api-notes.md` | API behaviours and gotchas learned the hard way |
| `.agents/skills/timesheets/` | Skill: generic workflow for logging time |
| `.agents/skills/invoicing/` | Skill: generic workflow for draft invoices from timeslips |
| `AGENTS.md` | Agent entry point (`CLAUDE.md` points to it) |
| `docs/mcp.md` | MCP server for Claude Code, Codex and ChatGPT |
| `docs/agent-rules.md` | Safety rules every agent should follow |

## Install

```bash
pip install -e ~/projects/freeagent-ai    # provides the `freeagent-ai` command and `import freeagent_ai`
```

## Plugin (Claude Code and Codex)

Installs the skills and the MCP server (run via `uvx`, so install [uv](https://docs.astral.sh/uv/) first). No checkout needed.

Claude Code:
```
/plugin marketplace add avalou-co/freeagent-ai
/plugin install freeagent-ai@freeagent-ai
```
Skills appear as `/freeagent-ai:timesheets` and `/freeagent-ai:invoicing`.

Codex:
```bash
codex plugin marketplace add avalou-co/freeagent-ai
```
then install `freeagent-ai` from the plugin list.

Manifests: `.claude-plugin/` (Claude Code), `.codex-plugin/` and `.agents/plugins/marketplace.json` (Codex), shared `.mcp.json` and `.agents/skills/`.

## Use

```bash
freeagent-ai login     # opens the approve page; the user logs in and clicks Approve
freeagent-ai status    # confirms stored credentials work
```

```python
from freeagent_ai import call

call("GET", "users/me")
call("POST", "timeslips", {"timeslip": {...}})
```

## Business-specific configuration

The business owns the specifics, wherever it keeps them (a repo, a prompt, a wiki), and gives agents that context alongside these docs:

- Fixed IDs (user, contacts, projects, tasks, bank account, categories) and your OAuth app's client ID.
- Defaults (hours per day, billing rate, VAT, payment terms, invoice reference format).
- Client-specific delivery rules (e.g. a portal instead of email).
- Rules such as "invoices are drafts only, never sent" and approval requirements beyond `docs/agent-rules.md`.

Install dev tools with `pip install -e ".[mcp,dev]"`, then run the checks CI runs on every PR: `ruff check .`, `ruff format --check .`, `pyright`, `pytest`.
