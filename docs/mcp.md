# MCP server

Typed tools over the client: `freeagent_get` and `find_contacts` (read-only), `create_contact`, `create_timeslip`, `create_draft_invoice` (always Draft, emails off), `create_expense` (optional local receipt file), `create_bill` (supplier bill with line items and optional attachment), `create_draft_estimate` (always Draft, never sent), `create_project`, `create_task`, `explain_bank_transaction` (one explanation per call). `update_created_entry` and `delete_created_entry` correct eligible entries created in the same task. Writes read back and return what FreeAgent holds.

The Claude Code and Codex plugins start it with `uvx` straight from GitHub (see `.mcp.json`), so no checkout or pip install is needed; `uv` must be installed. Run `freeagent-ai login` once first (e.g. `uvx --from git+https://github.com/avalou-co/freeagent-ai freeagent-ai login`); the server uses the same credentials file.

For local development: `pip install -e '.[mcp]'` and `freeagent-ai mcp`.

## GET pagination and rate limits

`freeagent_get(path)` aggregates all pages linked by the API. For example,
`freeagent_get("invoices?view=overdue&per_page=100")` returns the complete overdue
list without a manual page loop. Use `paginate=False` to retrieve just the
requested page. Do not manually follow pages after an automatic call, since
that would count records again.

GET HTTP 429 responses use bounded `Retry-After` retries. See
[API notes](api-notes.md#general) for retry and pagination limits.

## ChatGPT / remote HTTP

ChatGPT connects to remote servers only, so it needs `freeagent-ai mcp --http` (serves `http://127.0.0.1:8000/mcp`) reachable over public HTTPS, added as a custom connector in developer mode.

**HTTP mode requires a bearer token and fails closed.** Set `FREEAGENT_MCP_TOKEN` to a random secret of at least 32 ASCII characters before starting; without it the server refuses to start. Every request must send `Authorization: Bearer <token>`; others get `401` before any FreeAgent call. stdio mode needs no token.

```sh
export FREEAGENT_MCP_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
freeagent-ai mcp --http
```

Secure remote setup:

- Keep the default `--host 127.0.0.1` and expose it only through an HTTPS tunnel or reverse proxy. The token is sent in a header, so never serve it over plain HTTP across a network.
- Treat the token like a password: keep it out of shell history, repos and logs, and rotate it (restart with a new value) if it may have leaked. Anyone holding it can read and write your FreeAgent account.
- The connector client must be able to send a custom `Authorization: Bearer` header. If it cannot, do not use remote mode.
- This is a single static shared secret, not OAuth. Get an independent security review before relying on it for remote use.

## Correcting entries created in a task

Follow the [shared correction rules](agent-rules.md#correcting-entries-created-in-the-current-task).
After approval, pass `confirmed=True`:

```python
update_created_entry("timeslip", timeslip_url, {"hours": "7.5"}, True)
delete_created_entry("invoice", invoice_url, True)
```

The agent must verify that it created the entry during the current user request.
Ownership and human approval are governed by agent instructions, not server
provenance tracking. `confirmed` records the agent's assertion of user approval.
The server re-reads the entry before writing and applies these status gates:

- Timeslips: not billed on any invoice, and no running timer.
- Invoices and estimates: exactly `Draft`; no sending or status changes.
- Expenses: not rebilled on an invoice.
- Bills: wholly unpaid (zero `paid_value`), `Open`, `Overdue` or `Zero Value`, and not rebilled.

Supported changes:

| Type | Fields |
|------|--------|
| `timeslip` | `dated_on`, `hours`, `comment` |
| `invoice` | `dated_on`, `payment_terms_in_days`, `reference`, `comments`, `invoice_items` |
| `estimate` | `dated_on`, `reference`, `notes`, `estimate_items` |
| `expense` | `dated_on`, `gross_value`, `description`, `sales_tax_rate` |
| `bill` | `reference`, `dated_on`, `due_on`, `comments`, `bill_items` |

Invoice/estimate lines accept `id`, `description`, `item_type`, `quantity`, `price`
and `sales_tax_rate`. Estimate lines use the documented separate item POST/PUT
endpoints, followed by parent readback. An existing line's ID must belong to this entry; omitting
`id` adds a new line. Bill lines require an existing `url` belonging to this bill
and accept `description`, `total_value`, `total_value_ex_tax`, `sales_tax_rate`.
Bill values follow FreeAgent's documented tax semantics; do not guess tax treatment.
Line removal, relationship changes, attachments and status transitions are excluded.
Invoice updates always turn all three automatic email flags off.

Updates return a GET readback. Deletes return `deleted=True` only after GET reports
404; a 403, timeout or surviving record is an unverified outcome. A write or
readback failure returns an error directing the agent to inspect FreeAgent without
retrying or recreating the entry. Estimate line corrections can partially succeed
before a failure. The tools do not retry correction writes automatically or
remember prior attempts; the agent must reconcile any uncertain outcome.

There is no stored snapshot or atomic status check-and-write: the agent must
report conflicting edits, and external changes between the final GET and write
remain a race. These checks do not replace FreeAgent's permissions or built-in
duplicate-time protection.
