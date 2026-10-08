# freeagent-ai

[![skills.sh](https://img.shields.io/badge/skills.sh-freeagent--ai-black)](https://skills.sh/avalou-co/freeagent-ai)

Let AI agents (Claude Code, Codex, ChatGPT) work with your [FreeAgent](https://www.freeagent.com) account: log time, create contacts and draft invoices, record supplier bills and read your accounting data, with safety rules built in.

Nothing here is specific to one business. Your contact, project and bank-account IDs, rates and client rules stay with you and are given to the agent alongside these docs (see "Your business details").

## What you get

- **Skills**: ready-made workflows for logging time (`timesheets`) and creating draft invoices from timeslips (`invoicing`), recording expenses with receipts (`expenses`) and supplier bills (`bills`), draft estimates (`estimates`), and explaining bank transactions (`bank-reconcile`).
- **MCP server**: tools for reading FreeAgent data and finding and creating contacts, creating projects, tasks, timeslips, draft invoices, expenses, supplier bills, draft estimates and bank explanations.
- **Python client and CLI**: `freeagent-ai login`, `freeagent-ai status` and a small `call()` helper with automatic token refresh.
- **Safety rules**: agents confirm before writing, only create drafts, and never touch entries they did not create (`docs/agent-rules.md`).

## Quick start

### Claude Code

Requires [uv](https://docs.astral.sh/uv/).

```
/plugin marketplace add avalou-co/freeagent-ai
/plugin install freeagent-ai@freeagent-ai
```

The skills appear as `/freeagent-ai:timesheets`, `/freeagent-ai:invoicing`, `/freeagent-ai:expenses` and `/freeagent-ai:bills`, and the MCP server is set up for you.

### Codex

Requires [uv](https://docs.astral.sh/uv/).

```bash
codex plugin marketplace add avalou-co/freeagent-ai
```

Then install `freeagent-ai` from the plugin list.

### Other agents (skills.sh)

Install just the skills into any agent supported by [skills.sh](https://skills.sh/avalou-co/freeagent-ai):

```bash
npx skills add avalou-co/freeagent-ai
```

This copies the skills only. They need the `freeagent` MCP server's tools, so also add the server to your agent (requires [uv](https://docs.astral.sh/uv/)):

```json
{
  "mcpServers": {
    "freeagent": {
      "command": "uvx",
      "args": ["--from", "freeagent-ai[mcp] @ git+https://github.com/avalou-co/freeagent-ai", "freeagent-ai", "mcp"]
    }
  }
}
```

See `docs/mcp.md` for client-specific setup.

### ChatGPT and other MCP clients

See `docs/mcp.md` for running the MCP server.

## Connect your FreeAgent account

1. Create an OAuth app in the [FreeAgent developer dashboard](https://dev.freeagent.com) and note its client ID.
2. Log in once:

   ```bash
   freeagent-ai login     # opens the approve page; log in and click Approve
   freeagent-ai status    # confirms stored credentials work
   ```

Full steps, including the credentials file and re-login, are in `docs/auth.md`.

## Using it

Ask your agent in plain language, for example:

- "Log 7.5 hours a day on the Acme project for last week."
- "Create a draft invoice for this month's Acme timeslips."
- "Record this supplier bill and attach the PDF." / "Which bills are overdue?"
- "List my unexplained bank transactions and suggest explanations."

The agent shows you what it plans to create and waits for a clear yes before writing anything to FreeAgent.

### Command line and Python

Install the package to get the `freeagent-ai` command and the Python client:

```bash
pip install "freeagent-ai[mcp] @ git+https://github.com/avalou-co/freeagent-ai"
```

```python
from freeagent_ai import call

call("GET", "users/me")
call("POST", "timeslips", {"timeslip": {...}})
```

## Your business details

Give your agent the specifics it needs, wherever you keep them (a repo, a prompt, a wiki):

- Fixed IDs (user, contacts, projects, tasks, bank account, categories) and your OAuth app's client ID.
- Defaults (hours per day, billing rate, VAT, payment terms, invoice reference format).
- Client-specific delivery rules (e.g. a portal instead of email).
- Rules such as "invoices are drafts only, never sent" and any approvals beyond `docs/agent-rules.md`.

If something is missing, the agent should ask rather than guess.

## More documentation

| Doc | What |
|-----|------|
| `docs/auth.md` | OAuth setup, credentials file, refresh, re-login |
| `docs/mcp.md` | MCP server for Claude Code, Codex and ChatGPT |
| `docs/agent-rules.md` | Safety rules every agent should follow |
| `docs/api-notes.md` | API behaviours and gotchas learned the hard way |

## Contributing

Developer setup and checks are in `AGENTS.md`.
