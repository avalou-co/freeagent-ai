# MCP server

Shipped ChatGPT web/mobile workflows use discovered named remote tools under the
[design contract](#design-contract). The generic tools, Python/CLI setup and stdio
examples below describe local contributor/legacy clients only; they are never a
client-runtime fallback for hosted workflows.

Typed tools over the client: `freeagent_get` and `find_contacts` (read-only), `create_contact`, `create_timeslip`, `create_draft_invoice` (always Draft, emails off), `create_expense` (optional local receipt file), `create_bill` (supplier bill with line items and optional attachment), `create_draft_estimate` (always Draft, never sent), `create_project`, `create_task`, `explain_bank_transaction` (one explanation per call). `freeagent_post`, `freeagent_put` and `freeagent_delete` expose API writes directly. Convenience create tools read back automatically; generic write tools return the API response and the agent follows with `freeagent_get`.

The Claude Code and Codex plugins start it with `uvx` straight from GitHub (see `.mcp.json`), so no checkout or pip install is needed; `uv` must be installed. Run `freeagent-ai login` once first (e.g. `uvx --from git+https://github.com/avalou-co/freeagent-ai freeagent-ai login`); the server uses the same credentials file.

For local development: `pip install -e '.[mcp]'` and `freeagent-ai mcp`.

## Design contract

The MCP server is a window into the FreeAgent API. FreeAgent is the authority for
accounting and model validation: required fields, accepted values and attachments,
dates, amounts, tax, resource relationships, status transitions, payments and
whether a timeslip can be billed. Do not reproduce these rules locally, including
duplicate-billing guards, eligibility checks, field allowlists or accounting locks.
Send the request and report FreeAgent's response or validation error.

Every current and future shipped plugin workflow must function in ChatGPT on web
and mobile without a client interpreter, Python, shell, CLI, local filesystem or
assumed runtime. This applies to every implementation and skill/tool/doc change.
Use discovered named remote tools and documented supported host transports for
inputs and outputs. Server-side execution is allowed for API mechanics only; no
client runtime or server calculator may substitute for provider functionality.

Unsupported client delivery is unavailable capability: fail closed in hosted
discovery and packaging, record its status and withhold availability claims.
A protocol blob or successful developer/CI test is not proof of a usable client
artifact. Validate the generated package through discovery and authenticated
remote calls, including permissions, errors and artifact transport; obtain
independent architecture/client-contract review. The mandatory CI capability gate
must pass. Actual installed web/mobile evidence is a separate requirement before
claiming client delivery. See [contributor review guidance](../CONTRIBUTING.md).

The server owns API mechanics: authentication, keeping credentials private,
restricting requests to the FreeAgent API, JSON serialization, query encoding,
attachment encoding, pagination and bounded transport retries. MCP argument types
specify the tool's input shape; they must not add accounting constraints. Local
file-read failures and invalid API destinations are transport errors.

The agent owns user intent: obtain the required approval, use the business's actual
inputs, follow [agent rules](agent-rules.md), verify writes by reading back and
inspect uncertain outcomes before retrying. These responsibilities do not require
a server-side task ledger, reservation system or ownership lifecycle. Here,
“current task” means the current user request; a FreeAgent `task` is a billing
resource belonging to a project. Development work lives in GitHub issues and Projects.

Generic GET, POST, PUT and DELETE tools expose the API directly. Generic write
bodies are sent unchanged. Named convenience tools assemble documented API payloads
and read back after creation; their explicit defaults are listed below. Optional
empty strings in these helpers mean omission; use the generic tools when an explicit
empty value, another field or a different default is needed. Convenience defaults
must not become restrictions on the generic tools or local accounting validators.
All tools use the same API error handling. A successful create followed by a failed
readback must be investigated before another create.

## Tool audit

Hosted attachment descriptions distinguish metadata reads from add, update and
remove operations. Ownership checks are agent responsibilities. The payload invoice
helper sets Draft status and disables automatic emails; it accepts manual lines.

Hosted `duplicate_invoice`, `mark_invoice_as_sent` and `send_invoice_email` call
only their reviewed fixed provider endpoints and read affected invoices. All need
write scope and exact confirmation. The agent enforces the narrow
[invoice ownership/approval policy](invoicing.md#approved-invoice-delivery-and-duplication-policy).
The email tool accepts explicit recipient/sender/subject/body/sender-copy fields,
fixes expense-receipt inclusion off and accepts no templates or extra attachments.
It returns API acceptance separately from unavailable recipient delivery evidence.
No write retry, accounting state machine or ownership ledger is introduced.

The hosted `list_categories` adapter combines FreeAgent's four documented category
groups into its existing `categories` output. It preserves provider category fields
and fails incomplete reads when a group is missing or malformed; it does not select
categories or infer tax treatment.

All 19 registered tools were reviewed against the design contract. Named create
helpers share the same POST/readback implementation; local and hosted errors use
the same bounded provider-error formatter. This introduces no accounting validation. None performs
local accounting or model eligibility validation. This audit and the mocked tests
verify wrapper behavior; they do not independently test FreeAgent's accounting rules.

| Tool | API behavior and intentional convenience behavior |
| --- | --- |
| `freeagent_get` | GET any resource; aggregate pages by default, or return one page with `paginate=False`. |
| `freeagent_post` | POST the unchanged JSON body after the agent asserts approval; return the API response. |
| `freeagent_put` | PUT the unchanged JSON body after the agent asserts approval; return the API response. |
| `freeagent_delete` | DELETE after the agent asserts approval; return the API response without claiming verified absence. |
| `find_contacts` | GET all contacts and filter names and email locally, case-insensitively; no duplicate enforcement. |
| `create_contact` | POST supplied contact fields and read back; omitted payment terms use provider defaults, explicit zero is preserved. |
| `create_timeslip` | POST supplied timeslip fields and read back; no date, hours, relationship or duplicate checks. |
| `create_draft_credit_note` | POST supplied signed credit items using FreeAgent default Draft status, then read back; no issuance/email/allocation. |
| `issue_credit_note` | PUT fixed mark_as_sent transition after separate exact current-request Draft approval, then GET the credit; no email/allocation/refund or cancelled-credit reopening. |
| `create_credit_note_reconciliation` | POST separately approved allocation fields, then read reconciliation, credit note and invoice; destructive, non-idempotent, and subject to the narrow allocation ownership exception. |
| `create_draft_invoice` | POST invoice fields with automatic emails off; optionally request provider-generated timeslip lines, then read back. Relies on FreeAgent's default Draft status and unbilled-timeslip handling. |
| `create_draft_invoice_from_payload` | POST approved invoice object to fixed invoices endpoint with Draft and all automatic emails off, then read back. Manual lines/currency/provider inclusion strings remain unchanged; no accounting calculations or source eligibility validation. |
| `create_expense` | POST expense fields and optional encoded local attachment, then read back; no amount, tax or file-type validation. |
| `create_expense_from_payload` | POST one exact approved expense object unchanged, optionally encode a receipt, then read back; no tax arithmetic or provider field/model validation. Hosted new receipts use the bounded file-reference path. |
| `create_mileage_expense` | POST `category: Mileage`, supplied miles, vehicle and explicit reclaim flag, optional engine/VAT-receipt/project fields, then read back. No local rates, tax validation, amount calculation or duplicate enforcement. |
| `create_project` | POST project fields with Active status, day billing and Days budget units by default, then read back. |
| `create_task` | POST task fields with Active status and day billing by default; encode the project query parameter, then read back. |
| `create_draft_estimate` | POST Draft status and supplied line items, then read back; no line-item validation or sending. |
| `create_bill` | POST supplied bill fields and line items with an optional encoded local attachment, then read back. |
| `explain_bank_transaction` | POST supplied explanation fields and targets, then read back; FreeAgent validates the target combination and relationships. |

Attachments are base64 encoded with their filename and inferred MIME type
(`application/octet-stream` if unknown). FreeAgent decides whether to accept them.
Named create tools rely on the agent's approval workflow; generic write tools also
require `confirmed=True`, which records the agent's assertion, not independent
proof of user approval.

When adding or changing a tool, preserve this boundary, document any convenience
defaults here, and test that provider rejections are surfaced without local rules
or automatic write retries.

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

`freeagent_post(path, body, confirmed)`, `freeagent_put(path, body, confirmed)` and
`freeagent_delete(path, confirmed)` are thin API wrappers. Paths are relative to
`/v2/` or full FreeAgent API URLs, as with `freeagent_get`. Request bodies are
passed unchanged, including the API's root object. The tools constrain requests
to FreeAgent's API origin and reject path traversal; accounting, model, field and
relationship validation belong to FreeAgent.

Follow the [shared agent rules](agent-rules.md#correcting-entries-created-in-the-current-task).
After approval, send the exact API payload and read back the resource:

```python
freeagent_put(invoice_url, {"invoice": {"reference": "INV-2"}}, True)
freeagent_get(invoice_url)
freeagent_delete(invoice_url, True)
freeagent_get(invoice_url)  # HTTP 404 verifies absence
```

Use the provider's documented endpoint for line-item edits or status transitions;
there is no local line orchestration. For endpoints whose state is visible on a
parent resource, read that parent after writing. Generic write tools return the
API JSON response or the HTTP status for an empty response. They do not override
email settings, impose field allowlists, check billing/payment status, track task
ownership or verify readback automatically. Existing named create tools remain
convenience wrappers for their documented workflows.

`confirmed=True` records the agent's assertion of approval. Ownership follows agent
instructions. FreeAgent's HTTP status and JSON `errors` for 400, 409 and 422 are
reported as MCP tool errors; authentication response bodies are not exposed.
`freeagent_get` also exposes HTTP status, including 404 for deletion readback.
Inspect uncertain writes before retrying. The client does not retry writes on 429
or timeouts; it can refresh credentials once after a rejected 401.

Receipt interpretation and duplicate review use the [receipts workflow](../.agents/skills/receipts/SKILL.md).
`create_expense` and `create_bill` forward optional explicit `currency` unchanged;
this also appears in hosted schemas. No extraction or duplicate policy tool is
added. Hosted expense projections retain `receipt_reference` and available original,
native and manual tax fields for evidence comparison; they do not decide duplicates
or tax treatment. See the [hosted upload contract](receipts.md) for attachment boundaries.

## Credit-note helpers

`create_draft_credit_note` posts documented signed items with provider-default Draft
status and reads back; no issuance, email or allocation. `create_credit_note_reconciliation`
posts supplied allocation fields and reads reconciliation, credit note and invoice;
provider accounting validation is authoritative. Both are writes. The hosted
versions require confirmed=true; local helpers follow the shared approval rules.
See [allocation policy](credit-notes.md): the approved narrow exception permits
only allocation affecting a selected existing issued credit and invoice after
complete reads, exact preview and separate approval. It does not authorize issuing,
invoice edits, cash refunds or unrelated changes. No task ledger or local
eligibility validator is added.

`issue_credit_note` requires write scope and confirmed=true, issues a current-request
Draft with separate exact approval and GETs the credit for verification. It never
emails or allocates. Read related source evidence using named reads; inspect an
uncertain result before retrying. See [issuance policy](credit-notes.md#current-request-draft-issuance-policy).

## Bank attachment migration

API calls explicitly use `X-Api-Version: 2026-09-01`. The local generic API tools
already support the provider's separate attachment collection: GET metadata, POST
encoded files, PUT replacement/description or `_destroy`, then GET readback.
Their arbitrary approved bodies remain unchanged; no local attachment model/count
validator is added. The hosted audit adds four fixed named attachment tools with
numeric explanation/attachment IDs and bounded file references. POST and PUT
read the collection back automatically. This does not confer ownership or approval:
follow current-request rules for the explanation and existing attachment.
See [migration inventory, rollout and fallback](bank-attachments.md).

Hosted recurring profile reads use the fixed `list_recurring_invoices` and
`get_recurring_invoice` operations from the generated registry audit. Both are
read-only and preserve shared scope, account isolation and pagination mechanics.
The envelope adds collection-completion time; provider fields remain unchanged or
absent. Local clients can use the unchanged generic GET. The packaged workflow uses
only named remote reads and [provider-returned evidence](recurring-revenue.md); no
recurrence expansion, calculator or payment scenario is added.

## Month-end read coverage

The read-only month-end skill composes existing named company, bank, invoice,
bill, timeslip and expense reads; no accounting/checking tool is introduced.
Collection and detail envelopes for bank accounts/transactions, invoices, bills,
timeslips and expenses now include collected_at UTC after a successful read.
This is server collection metadata, not provider financial data or an atomic
snapshot. Existing fields, filters, pagination, authorization and errors remain
unchanged. See [month-end evidence limits](month-end.md).

## Document PDF delivery

Named PDF reads identify the selected document and return the registered card.
Its one Download PDF action calls a UI-only refresh tool through authenticated
MCP, requires advertised host openLinks support for ui/open-link navigation,
checks the immutable original account/document context and obtains a short,
single-use delegated capability. The branded browser page clears the fragment
and POST-fetches the PDF once, shows preparation, then exposes a persistent ready
control and automatically requests the browser download. It retains only bounded
already received bytes in page memory for manual download; no grant is replayed.
No second click or browser login is required for the initial request. Browser cookies never select another account. This is narrow bearer
capability authority, not a browser identity check. [Full contract and remaining
installed-client verification](documents.md).
