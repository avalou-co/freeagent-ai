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
| `clients` | Finding or creating contacts, projects and tasks; setting up a new client |
| `timesheets` | Logging time as timeslips for a date range |
| `credit-notes` | Reviewed draft credit notes and policy-gated invoice allocation |
| `invoicing` | Creating draft invoices, optionally from timeslips |
| `receipts` | Extracting and reviewing receipt images/PDFs before expense or bill creation |
| `expenses` | Recording expense claims with receipts |
| `mileage` | Recording reviewed mileage inputs and provider-calculated claim results |
| `estimates` | Creating draft estimates/quotes with line items |
| `bills` | Recording supplier bills, listing unpaid or overdue ones |
| `bank-reconcile` | Listing unexplained bank transactions and proposing explanations |
| `cash-flow` | Read-only provider bank balances and outstanding records |
| `profitability` | Read-only provider project, budget, time and billing records |
| `recurring-revenue` | Read-only FreeAgent recurring invoice profiles and provider-reported dates/statuses |
| `tax-overview` | Read-only provider tax amounts, filing/payment deadlines and status |
| `reports` | Read-only P&L, balance sheet, trial balance, cash, overdue invoices and bills |
| `invoice-status` | Read-only: list invoices by status/contact/date, show payment status, draft overdue chasers |

## Calling the API

```python
from freeagent_ai import call

call("GET", "users/me")
```

If the `freeagent` MCP tools are available, prefer them (`docs/mcp.md`). Or from the shell: `freeagent-ai status`, `freeagent-ai login`.

## Business specifics

This repo is generic. IDs, rates, defaults and client rules come from the business's own instructions. If they are missing, ask; never guess.

## Work tracking

Track development tasks in GitHub issues and GitHub Projects. Do not create
repository milestone or task tracking files.

## MCP design

Follow the [MCP design contract](docs/mcp.md#design-contract). FreeAgent owns
accounting and model validation; tools provide API mechanics and agents handle
approval and verification. Keep the tool audit current when changing MCP tools.

## Development

Install dev tools with `pip install -e ".[mcp,dev]"`, then run the checks CI runs on every PR: `ruff check .`, `ruff format --check .`, `pyright`, `pytest`.
Claude Code loads the skills through the `freeagent-ai` plugin (`.claude-plugin/`), as `/freeagent-ai:<name>`. Develop with `claude --plugin-dir .`.

## Public repository boundary

This repository is public. Keep private deployment identifiers, internal runbooks,
private repository links, credentials and real accounting/customer data out of
source, tests, issues, PR text and CI artifacts. Use synthetic test values and
protected deployment inputs. Public product branding, service URLs and support
contacts are intentional. Keep operator-specific configuration and operational
evidence in the private deployment repository. Do not print private destinations
in public build summaries or upload container build records containing them.

After a repository history cleanup, use a fresh clone or an explicitly migrated
worktree. Never push pre-cleanup branches or merge old history back into the repo.
