# AGENTS.md

How AI agents use this repo to work with a FreeAgent account through its API.

## Read first

- `docs/agent-rules.md`: safety rules. Apply them to every task.
- `docs/api-notes.md`: request bodies and API quirks. Read before any write.
- `docs/auth.md`: login and credentials. Read if `freeagent-ai status` fails.

## Skills

Each task has a workflow in `.agents/skills/<name>/SKILL.md`. Load the one that matches:

| Skill | Use for |
|-------|---------|
| `timesheets` | Logging timeslips for a date range |
| `invoicing` | Draft invoices, optionally from timeslips |
| `expenses` | Expense claims with receipts |
| `estimates` | Draft estimates and quotes |
| `bills` | Supplier bills, and listing unpaid or overdue ones |

## Calling the API

Use the `freeagent` MCP tools if you have them (`docs/mcp.md`). Otherwise use Python:

```python
from freeagent_ai import call

call("GET", "users/me")
```

## Business details

This repo holds no business data. IDs, rates, defaults and client rules come from the business's own instructions. If one is missing, ask.

## Development

Install with `pip install -e ".[mcp,dev]"`. CI runs `ruff check .`, `ruff format --check .`, `pyright` and `pytest` on every PR.

Claude Code loads the skills through the plugin in `.claude-plugin/` as `/freeagent-ai:<name>`. Run `claude --plugin-dir .` to test local changes.
