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
| `credit-notes` | Reviewed draft credit notes, separately approved current-request issuance and invoice allocation |
| `invoicing` | Draft creation, reviewed new-Draft duplication and separately approved current-request status/email actions |
| `receipts` | Extracting and reviewing receipt images/PDFs before expense or bill creation |
| `expenses` | Recording expense claims with receipts |
| `mileage` | Recording reviewed mileage inputs and provider-calculated claim results |
| `documents` | Experimental local PDF diagnostics; unavailable in hosted ChatGPT web/mobile |
| `estimates` | Creating draft estimates/quotes with line items |
| `bills` | Recording supplier bills, listing unpaid or overdue ones |
| `bank-reconcile` | Listing unexplained bank transactions and proposing explanations |
| `cash-flow` | Read-only provider bank balances and outstanding records |
| `profitability` | Read-only provider project, budget, time and billing records |
| `recurring-revenue` | Read-only FreeAgent recurring invoice profiles and provider-reported dates/statuses |
| `payroll` | Read-only UK payroll filing and payment evidence; employee payslips omitted |
| `tax-overview` | Read-only provider tax amounts, filing/payment deadlines and status |
| `month-end` | Read-only month-end bookkeeping evidence and approved-workflow handoffs |
| `reports` | Read-only P&L, balance sheet, trial balance, cash, overdue invoices and bills |
| `invoice-status` | Read-only: list invoices by status/contact/date, show payment status, draft overdue chasers |

## Calling the API

Shipped ChatGPT web/mobile workflows use the discovered named remote MCP tools.
Do not fall back to a client interpreter, local executor, shell or filesystem.

The following is local contributor/legacy-client usage only, not a plugin user
workflow or fallback for web/mobile:

```python
from freeagent_ai import call

call("GET", "users/me")
```

Local contributors can also use `freeagent-ai status` and `freeagent-ai login`.
See [the MCP contract](docs/mcp.md#design-contract) for hosted tool boundaries.

## Business specifics

This repo is generic. IDs, rates, defaults and client rules come from the business's own instructions. If they are missing, ask; never guess.

## Work tracking

Track development tasks in GitHub issues and GitHub Projects. Do not create
repository milestone or task tracking files.

## MCP design

Follow the [MCP design contract](docs/mcp.md#design-contract). FreeAgent owns
accounting and model validation; tools provide API mechanics and agents handle
approval and verification. Keep the tool audit current when changing MCP tools.

## Interpreter-free plugin contract

This applies to all current and future implementations, including skill, tool,
artifact and documentation changes. Every shipped plugin workflow must work in
ChatGPT on web and mobile without a client interpreter, Python, shell, CLI, local
filesystem or assumed runtime. Use discovered named remote tools and documented,
supported host input/output transports. Backend code may perform API mechanics
only under the MCP design contract; it cannot substitute an accounting engine.

Unavailable tools or unsupported client artifact delivery must fail closed: omit
them from hosted discovery and packages, record the unavailable capability and
keep claims accurate. Preserve separate prototype diagnostics without presenting
them as product availability. Test the generated package, discovery, authenticated
remote calls, permissions/errors and usable artifact contract. Tests executing on
a developer/CI interpreter do not prove client support. Require the existing
mandatory CI capability gate and independent architecture/client-contract review;
record actual installed web/mobile evidence separately before claiming delivery.
See [contributor review guidance](CONTRIBUTING.md).

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
