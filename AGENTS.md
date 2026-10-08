# AGENTS.md

Entry point for AI agents using this repo to work with a FreeAgent account through the API.

## Read first

- `docs/agent-rules.md`: safety rules. Always apply.
- `docs/auth.md`: OAuth, credentials file, re-login. Read if `freeagent-ai status` fails.
- `docs/api-notes.md`: API behaviours and gotchas. Read before any write.

## Skills

Task workflows live in `.agents/skills/<name>/SKILL.md`. Load the one that matches the task:

| Skill | Use for |
|-------|---------|
| `timesheets` | Logging time as timeslips for a date range |
| `invoicing` | Creating draft invoices, optionally from timeslips |
| `estimates` | Creating draft estimates/quotes with line items |

## Calling the API

```python
from freeagent_ai import call

call("GET", "users/me")
```

If the `freeagent` MCP tools are available, prefer them (`docs/mcp.md`). Or from the shell: `freeagent-ai status`, `freeagent-ai login`.

## Business specifics

This repo is generic. IDs, rates, defaults and client rules come from the business's own instructions. If they are missing, ask; never guess.

## Development

Install dev tools with `pip install -e ".[mcp,dev]"`, then run the checks CI runs on every PR: `ruff check .`, `ruff format --check .`, `pyright`, `pytest`.
Claude Code loads the skills through the `freeagent-ai` plugin (`.claude-plugin/`), as `/freeagent-ai:<name>`. Develop with `claude --plugin-dir .`.
