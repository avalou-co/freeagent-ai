# API notes

Learned from real use. All paths are relative to `https://api.freeagent.com/v2/`.

## Projects and tasks

- List with `GET projects?contact=<contact url>&view=active` and `GET tasks?project=<project url>&view=active`; match names there before creating, so timeslips and invoices can use the URLs.
- `POST projects` body: `{"project": {"contact", "name", "status": "Active", "currency", "normal_billing_rate", "billing_period"}}`, plus `budget` and `budget_units` (`Hours`, `Days` or `Monetary`) if budgeted. Rates and budget are strings.
- `POST tasks?project=<project url>` body: `{"task": {"name", "status": "Active", "billing_rate", "billing_period"}}`. The project goes in the query string, not the body. `billing_period` is `hour` or `day`.

## Timeslips

- `POST timeslips` body: `{"timeslip": {"task", "project", "user", "dated_on", "hours"}}` with full resource URLs and `hours` as a string.
- `GET timeslips?from_date=&to_date=&per_page=100` returns all linked pages with this client; filter by range and check for existing dates before posting.
- A per-day task is billed per day, so a full working day's hours equals one billable day. Check the task's `billing_period` and rate first.

## Invoices

- `POST invoices` with `project`, `contact`, `include_timeslips: "billed_grouped_by_timeslip"` pulls the project's unbilled timeslips in as lines.
  **Do not also send a placeholder `invoice_items` entry**: it is added on top as an extra line and inflates the total.
- A created invoice is `Draft`. Set all three `send_new_invoice_emails`, `send_reminder_emails`, `send_thank_you_emails` to `false`.
- Removing a line: `DELETE invoice_items/<id>` works. `PUT` with `_destroy` (`1` or `true`) did not remove it.
- Listing: `GET invoices?view=` `open_or_overdue`, `open`, `overdue`, `draft`, `paid`; filters `contact=<url>`, `from_date`, `to_date`. Payment fields `status`, `due_on`, `total_value`, `due_value`, `currency`. The client follows linked pages automatically; use `paginate=False` with `per_page=100&page=N` for manual paging.
- Reading past invoices (`GET invoices?project=...`, then `GET invoices/<id>`) is the best source for reference format, terms, description style and VAT.
- Verify after creating: status, line count, net = quantity x rate, VAT, emails off.

## Expenses

- `POST expenses` body: `{"expense": {"user", "category", "dated_on", "gross_value", "description"}}` with full resource URLs and `gross_value` as a string including VAT. Expenses are negative (`"-12.50"`).
- `sales_tax_rate` (e.g. `"20.0"`) sets VAT; the category may need to allow it.
- Receipt: `attachment: {file_name, content_type, data}` with `data` base64. Accepts PDF, PNG, JPG, GIF with a size limit; the tool allows only those types.
- Categories: `GET categories`; admin expenses categories are the ones valid for expense claims.
- Check `GET expenses?from_date=&to_date=` for duplicates before posting.

## Contacts

- `POST contacts` body: `{"contact": {...}}`. Needs `organisation_name`, or both `first_name` and `last_name`. Address fields are `address1`, `town`, `postcode`, `country`; terms are `default_payment_terms_in_days`.
- `GET contacts?view=all&per_page=100&page=N` lists contacts; there is no name search, so filter client-side (`find_contacts` does) and check for duplicates before creating.
- Use the created contact's URL as `contact` when creating invoices.

## Estimates

- `POST estimates` body: `{"estimate": {"contact", "dated_on", "currency", "estimate_items": [{"description", "item_type", "quantity", "price"}]}}`; `project` is optional. Amounts are strings.
- Create with `status: "Draft"`. Estimates have no email flags; sending is a separate action this repo never takes.
- List with `GET estimates?contact=...` (or `?project=...`) and copy reference style from the latest.
- Not yet supported: converting an approved estimate to an invoice.
- Verify after creating: status, line count, net = quantity x price.

## Bills

- `POST bills` body: `{"bill": {"contact", "reference", "dated_on", "due_on", "bill_items": [{"category", "description", "total_value", "sales_tax_rate"}]}}` with full resource URLs and decimal strings; `total_value` includes taxes; use `total_value_ex_tax` for a net line amount.
- `sales_tax_rate` (e.g. `"20.0"`) sets VAT per line; the category may need to allow it.
- Attachment: `attachment: {file_name, content_type, data}` with `data` base64. Accepts PDF, PNG, JPG, GIF; the tool allows only those types.
- Unpaid and overdue: `GET bills?view=open` and `GET bills?view=overdue`.
- Categories: `GET categories`. Check `GET bills?from_date=&to_date=` for the same reference before posting.

## Bank explanations

- `GET bank_accounts` lists accounts; `GET bank_transactions?bank_account=<url>&view=unexplained` lists transactions still needing explanation.
- `POST bank_transaction_explanations` body: `{"bank_transaction_explanation": {"bank_transaction", "dated_on", "gross_value", ...}}` plus one of `category` (URL), `paid_invoice` (URL) or `paid_bill` (URL). `gross_value` carries the transaction's sign.
- Match invoices/bills by amount and contact: `GET invoices?view=open` / `GET bills?view=open`. A partial explanation may leave the transaction partly unexplained; re-read it afterwards.
- Category URLs and any VAT treatment come from the business's own instructions; never guess them.

## General

- HTTPX2 handles API requests and parses Link headers; Tenacity manages retry scheduling and limits.
- `call("GET", path)` and MCP `freeagent_get(path)` follow `Link: rel=next` automatically and combine top-level list fields into the original response object. Filters come from the server's next link; detail/report responses without a next link are unchanged. Use `paginate=False` for a single page or manual paging. Start without a `page` parameter to retrieve the complete collection; an explicit page starts aggregation there. Non-list metadata remains from the first page.
- Pagination refuses links outside the API origin or `/v2/`, repeated links, inconsistent list responses, and collections exceeding 1,000 pages. Failures raise instead of returning partial results.
- GET HTTP 429 responses retry up to three times per page. `Retry-After` seconds and HTTP dates are honoured; missing/invalid values use Tenacity exponential backoff (1, 2, then 4 seconds). A requested wait over 60 seconds raises immediately rather than retrying early. Writes are not retried on 429. Other rate-limit/server failures raise `urllib.error.HTTPError`; the body usually names the problem.
- Always read back after a write and report what FreeAgent holds, not what you sent.

## Reports

Read-only via `freeagent_get`.

- `accounting/profit_and_loss/summary?from_date=&to_date=`
- `accounting/balance_sheet?as_at_date=`
- `accounting/trial_balance/summary?from_date=&to_date=`
- `invoices?view=overdue`, `bills?view=overdue` (client aggregates linked pages; total per currency)
- `bank_accounts` for balances (cash).

## Direct API writes

Use `freeagent_post`, `freeagent_put` or `freeagent_delete` with the provider's
path and payload. They return the API response; follow with `freeagent_get` on the
resource or parent to verify the write. FreeAgent owns accounting validation,
including duplicate-time-billing protection. No local status, payment or line
relationship checks are applied.

See [agent rules](agent-rules.md#correcting-entries-created-in-the-current-task) and
[MCP write tools](mcp.md#correcting-entries-created-in-a-task).
API contracts: [HTTP verbs](https://dev.freeagent.com/docs/introduction),
[timeslips](https://dev.freeagent.com/docs/timeslips),
[invoices](https://dev.freeagent.com/docs/invoices),
[estimates](https://dev.freeagent.com/docs/estimates),
[expenses](https://dev.freeagent.com/docs/expenses),
[bills](https://dev.freeagent.com/docs/bills).
