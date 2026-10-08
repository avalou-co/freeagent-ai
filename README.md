# freeagent-ai

[![skills.sh](https://img.shields.io/badge/skills.sh-freeagent--ai-black)](https://skills.sh/avalou-co/freeagent-ai)

Lets AI agents such as Claude Code, Codex and ChatGPT work in your [FreeAgent](https://www.freeagent.com) account. They can log time, add contacts, draft invoices and estimates, record expenses and supplier bills, and read your accounts.

The agent shows you what it plans to write and waits for your yes. It only creates drafts and leaves entries it did not make alone (`docs/agent-rules.md`).

## What is in the repo

- `Skills` for timesheets, invoicing, expenses, bills and estimates.
- `An MCP server` with tools to read FreeAgent and create entries (`docs/mcp.md`).
- `A CLI and Python client`: `freeagent-ai login`, `freeagent-ai status` and a `call()` helper that refreshes tokens for you.

## Install

All options need [uv](https://docs.astral.sh/uv/).

`Claude Code.` This sets up the skills and the MCP server:

```
/plugin marketplace add avalou-co/freeagent-ai
/plugin install freeagent-ai@freeagent-ai
```

The skills appear as `/freeagent-ai:<name>`, for example `/freeagent-ai:timesheets`.

`Codex.` Add the marketplace, then install `freeagent-ai` from the plugin list:

```bash
codex plugin marketplace add avalou-co/freeagent-ai
```

`Other agents.` [skills.sh](https://skills.sh/avalou-co/freeagent-ai) copies the skills only:

```bash
npx skills add avalou-co/freeagent-ai
```

The skills call the MCP server's tools, so add the server to your agent too:

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

`ChatGPT.` It needs the server over HTTPS. See `docs/mcp.md`.

## Connect your FreeAgent account

Create an OAuth app in the [FreeAgent developer dashboard](https://dev.freeagent.com), then log in once:

```bash
freeagent-ai login
```

```bash
freeagent-ai status
```

`login` opens FreeAgent in your browser for you to approve, and `status` checks the saved credentials work. `docs/auth.md` covers the credentials file and redirect URI.

## Using it

Ask your agent in plain language:

- "Log 7.5 hours a day on the Acme project for last week."
- "Create a draft invoice for this month's Acme timeslips."
- "Record this supplier bill and attach the PDF."
- "Which bills are overdue?"

To use the Python client directly:

```bash
pip install "freeagent-ai[mcp] @ git+https://github.com/avalou-co/freeagent-ai"
```

```python
from freeagent_ai import call

call("GET", "users/me")
```

## Your business details

Nothing in this repo is specific to one business. Give your agent the rest wherever you keep it, such as a repo, a prompt or a wiki:

- IDs for your user, contacts, projects, tasks, bank account and categories, plus your OAuth client ID.
- Defaults such as hours per day, rates, VAT, payment terms and invoice reference format.
- Client rules, for example "submit through their portal, not by email".
- Any approvals you want on top of `docs/agent-rules.md`.

The agent asks when something is missing.

## Contributing

`AGENTS.md` has the developer setup and the checks CI runs.
