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

- Named hosted `duplicate_invoice` uses the fixed provider duplicate endpoint and
  reads the new Draft and original source. `mark_invoice_as_sent` and
  `send_invoice_email` are separately approved current-request-only actions under
  the [invoice policy](invoicing.md#approved-invoice-delivery-and-duplication-policy).
  Sending requires explicit reviewed fields, disables expense-receipt inclusion,
  and does not accept templates/extra attachments. API acceptance is not recipient
  delivery. All action helpers read back and report uncertain outcomes without
  replay; provider error bodies are withheld to protect email content.

- Contract checked 2026-10-26: [provider invoice creation](https://dev.freeagent.com/docs/invoices).
  Named remote `create_draft_invoice_from_payload` accepts manual `invoice_items`,
  explicit `currency` and documented `include_timeslips`, `include_estimates` and
  `include_expenses` modes. It fixes Draft and automatic emails off and reads back;
  other fields pass unchanged. Nested references are full provider URLs.
- `include_estimates` includes open/approved estimates; `include_expenses` includes
  expenses, bills and bank account entries. Grouping modes do not select individual
  IDs: review the whole project scope before approval, stop on unavailable evidence,
  and reread actual invoice lines and source states afterwards. No custom tax/totals
  or eligibility calculation is provided. See [invoice contract](invoicing.md).

- `POST invoices` with `project`, `contact`, `include_timeslips: "billed_grouped_by_timeslip"` pulls the project's unbilled timeslips in as lines.
  **Do not also send a placeholder `invoice_items` entry**: it is added on top as an extra line and inflates the total.
- A created invoice is `Draft`. Set all three `send_new_invoice_emails`, `send_reminder_emails`, `send_thank_you_emails` to `false`.
- Removing a line: `DELETE invoice_items/<id>` works. `PUT` with `_destroy` (`1` or `true`) did not remove it.
- Listing: `GET invoices?view=` `open_or_overdue`, `open`, `overdue`, `draft`, `paid`; filters `contact=<url>`, `from_date`, `to_date`. Payment fields `status`, `due_on`, `total_value`, `due_value`, `currency`. The client follows linked pages automatically; use `paginate=False` with `per_page=100&page=N` for manual paging.
- Reading past invoices (`GET invoices?project=...`, then `GET invoices/<id>`) is the best source for reference format, terms, description style and VAT.
- Verify after creating: provider-returned status, item identities/count, tax and totals, currency and emails off. Do not compute invoice totals or taxes locally.

## Expenses

- `POST expenses` body: `{"expense": {"user", "category", "dated_on", "gross_value", "description"}}` with full resource URLs and `gross_value` as a string including VAT. Expenses are negative (`"-12.50"`).
- `sales_tax_rate` (e.g. `"20.0"`) sets VAT; the category may need to allow it.
- Receipt: `attachment: {file_name, content_type, data}` with `data` base64. FreeAgent documents PDF, PNG, JPG and GIF with a 5 MB limit. Local tools encode the supplied file and leave acceptance to FreeAgent; hosted downloads enforce the bounded type contract in [receipt handling](receipts.md).
- Categories: `GET categories`; admin expenses categories are the ones valid for expense claims.
- Check both expenses and bills, across all pages, before recording a receipt. Hosted expense reads retain `receipt_reference` for reference matching. They also preserve documented native/manual tax fields separately from original-currency amounts; do not compare a native-currency manual tax amount directly with foreign-currency printed tax. Missing fields are unavailable, never zero. See the [receipts workflow](../.agents/skills/receipts/SKILL.md).

- Exact-tax expense creates use `create_expense_from_payload(expense=...)` with the approved provider object unchanged; hosted receipt files use `receipt`, not embedded attachment bytes or a local path. Nested resource values are full provider URLs. Manual/native tax amounts are company-native currency; foreign-currency `sales_tax_rate` is ignored by FreeAgent. Preserve exact supplied values and inspect readback, without tax/FX calculations. See [receipt currency contract](receipts.md).

## Mileage expenses

- Provider contract checked 2026-10-26: [expenses and mileage settings](https://dev.freeagent.com/docs/expenses).
- `GET expenses/mileage_settings` returns date intervals for `mileage_rates` and
  `engine_type_and_size_options`. Fetch for the linked account; documentation
  examples are not current rate guidance. Each rate interval has `value` containing
  vehicle-specific `basic_rate`/`additional_rate` and `basic_rate_limit`.
- `POST expenses` with root `expense`, `category: "Mileage"`, `user`, `dated_on`,
  `description`, `mileage` (decimal **miles**) and `vehicle_type` (`Car`, `Motorcycle`
  or `Bicycle`). `reclaim_mileage: 1` requests provider AMAP reimbursement; `0` is
  rebill-only, not an ordinary reimbursed claim. Do not send a guessed gross value.
- Resolve `engine_type`/`engine_size` against the journey's date and explicitly
  establish `have_vat_receipt`/VAT treatment. Provider engine defaults are not facts
  about the user's vehicle. `project` is optional; confirm rebilling separately.
- FreeAgent calculates the amount. Preview exact API inputs before approval, then
  verify returned mileage, claimant, currency, engine, reclaim and project fields.
  Report provider-returned amount/rate values with their signs; absent values remain
  unavailable. Do not derive reimbursement, rate bands or expected balances locally.
- The documented API accepts miles only and offers no mileage quote/preview endpoint.
  Ask for miles if the source uses kilometres or other units; do not convert or
  relabel the distance. There is no custom preview engine or client runtime.
- Settings are provider evidence, not a determination of eligibility. Unsupported
  reimbursement arrangements or missing vehicle/tax facts require a user decision,
  not an invented rate or alternate accounting treatment.
- Use one create per approved journey. On partial failure, stop and inspect before
  resuming. Do not retry an uncertain write or silently change existing claims.

## Contacts

- `POST contacts` body: `{"contact": {...}}`. Needs `organisation_name`, or both `first_name` and `last_name`. Address fields are `address1`, `town`, `postcode`, `country`; terms are `default_payment_terms_in_days`.
- `GET contacts?view=all&per_page=100&page=N` lists contacts; there is no name search, so filter client-side (`find_contacts` does) and check for duplicates before creating.
- Use the created contact's URL as `contact` when creating invoices.

## Estimates

- `POST estimates` body: `{"estimate": {"contact", "dated_on", "currency", "estimate_items": [{"description", "item_type", "quantity", "price"}]}}`; `project` is optional. Amounts are strings.
- Create with `status: "Draft"`. Estimates have no email flags; sending is a separate action this repo never takes.
- List with `GET estimates?contact=...` (or `?project=...`) and copy reference style from the latest.
- Draft invoice creation can request provider `include_estimates` modes for open/approved project estimates; this is not an individual estimate-ID conversion or permission to issue/send. See [invoice contract](invoicing.md).
- Verify after creating: provider-returned status, lines, net, tax and gross against the approved inputs or explicitly sourced expectations; never recalculate accounting amounts.

## Bills

- `POST bills` body: `{"bill": {"contact", "reference", "dated_on", "due_on", "bill_items": [{"category", "description", "total_value", "sales_tax_rate"}]}}` with full resource URLs and decimal strings; `total_value` includes taxes; use `total_value_ex_tax` for a net line amount.
- `sales_tax_rate` (e.g. `"20.0"`) sets VAT per line; the category may need to allow it.
- Attachment: `attachment: {file_name, content_type, data}` with `data` base64. FreeAgent documents PDF, PNG, JPG and GIF with a 5 MB limit. Local tools leave file acceptance to FreeAgent; hosted downloads enforce the [receipt transport contract](receipts.md).
- Unpaid and overdue: `GET bills?view=open` and `GET bills?view=overdue`.
- Categories: `GET categories`. Check `GET bills?from_date=&to_date=` for the same reference before posting.

## Bank explanations

- `GET bank_accounts` lists accounts; `GET bank_transactions?bank_account=<url>&view=unexplained` lists transactions still needing explanation.
- `POST bank_transaction_explanations` body: `{"bank_transaction_explanation": {"bank_transaction", "dated_on", "gross_value", ...}}` plus one of `category` (URL), `paid_invoice` (URL) or `paid_bill` (URL). `gross_value` carries the transaction's sign.
- Match invoices/bills by amount and contact: `GET invoices?view=open` / `GET bills?view=open`. A partial explanation may leave the transaction partly unexplained; re-read it afterwards.
- Category URLs and any VAT treatment come from the business's own instructions; never guess them.

### Versioned bank attachments

The client explicitly sends `X-Api-Version: 2026-09-01` on authenticated API
requests (local and hosted), including pagination and writes; OAuth exchanges are
unchanged. This opts into the documented bank-attachment contract before the
1 December 2026 default change. See [migration and release gates](bank-attachments.md).

- Bank transactions and explanations can return plural `attachments`; transaction
  responses may nest `bank_transaction_explanations`. Hosted reads retain these
  relationships and safe metadata. Legacy singular `attachment` is also preserved
  when returned; missing fields remain unknown, not evidence of no attachment.
- Use `GET bank_transaction_explanations/<id>/attachments` for complete metadata.
  The provider's explanation response may contain only attachment URLs. Signed
  `content_src`/thumbnail URLs, expiry values and content are omitted by hosted tools.
- Add via `POST` to that same collection with `{"attachments": [{"file_name": ...,
  "content_type": ..., "data": "base64", "description": ...}]}`. Update via `PUT`
  with the existing attachment's `url`; remove via `PUT` with that `url` and
  `"_destroy": "true"`. Do not put legacy `attachment` on an explanation write.
- The provider supports 10 files per call and 50 per explanation. Hosted named
  writes handle one file per invocation using the existing bounded receipt
  downloader; provider count/model validation remains authoritative. Local generic
  writes support the documented payload unchanged, with locally encoded files.
- Current-request ownership applies to both the explanation and any existing
  attachment changed/removed. Do not attach to an explanation from an earlier
  request under the current policy. Preview exact file/description/IDs, get approval,
  read the collection after each write and compare metadata/counts to the preview.
  Empty successful responses do not prove a change. Stop and inspect timeouts,
  rejected/partial batches, missing attachments and failed readbacks; never replay
  an uncertain upload. Keep existing attachments unless their removal was approved.

## General

- HTTPX2 handles API requests and parses Link headers; Google API Core's `HTTPIterator` follows pages through the existing transport. A shared adapter validates every next destination, enforces completeness limits, and merges list fields. Tenacity manages local retry scheduling and limits. Hosted requests retain their account binding and shared absolute deadline.
- `call("GET", path)` and MCP `freeagent_get(path)` follow `Link: rel=next` automatically and combine top-level list fields into the original response object. Filters come from the server's next link; detail/report responses without a next link are unchanged. Use `paginate=False` for a single page or manual paging. Start without a `page` parameter to retrieve the complete collection; an explicit page starts aggregation there. Non-list metadata remains from the first page.
- Pagination refuses links outside the API origin or `/v2/`, repeated links, inconsistent list responses, and collections exceeding 1,000 pages. Failures raise instead of returning partial results.
- GET HTTP 429 responses retry up to three times per page. `Retry-After` seconds and HTTP dates are honoured; missing/invalid values use Tenacity exponential backoff (1, 2, then 4 seconds). A requested wait over 60 seconds raises immediately rather than retrying early. Writes are not retried on 429. Other rate-limit/server failures raise `urllib.error.HTTPError`; the body usually names the problem.
- Always read back after a write and report what FreeAgent holds, not what you sent.

## Reports

Read-only via `freeagent_get`.

- `accounting/profit_and_loss/summary?from_date=&to_date=`
- `accounting/balance_sheet?as_at_date=`
- `accounting/trial_balance/summary?from_date=&to_date=`
- `invoices?view=overdue`, `bills?view=overdue` (the client aggregates linked pages while preserving provider amounts and currencies; do not derive local totals)
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

## Hosted financial evidence reads

- Fixed credit-note and credit-note-reconciliation list/get tools retain signed
  revenue, outstanding refund and allocation evidence. Allocations are not cash
  refunds; never subtract allocated credits twice. Create/issue/allocation writes
  remain outside these read-only additions.
- Hosted task reads retain `is_billable`; timeslips retain the actual provider
  `billed_on_invoice` field and nested `timer` (`running`, `start_from`). A linked
  Draft invoice is billed time for unbilled-work selection. Resolve running timers.
- Project reads retain `hours_per_day` and provider budget fields without deriving
  budget usage. Expense/bill reads retain project, rebilling and net/tax evidence. See [field coverage and incomplete reads](analysis.md#hosted-field-coverage).

## Tax returns (read-only)

See [tax evidence rules](tax-overview.md) for verified paths, date identifiers,
user-scoped self-assessment, distinct payment/filing dates, partial-payment limits
and unavailable residuals. No custom tax/forecast calculations, filing or payment
action is added.

## Credit notes and invoice allocations

Use the [credit workflow and allocation policy](credit-notes.md). Provider creates credit
notes as Draft. Named helper forwards signed credit_note_items and reads back;
`issue_credit_note` separately calls fixed PUT credit_notes/:id/transitions/mark_as_sent
and reads the credit back. Only a current-request-created Draft with separate exact
approval is in scope; email/reopening cancelled credits are excluded. Reconciliations use
POST credit_note_reconciliations with credit_note/invoice/gross_value; helper reads
reconciliation, credit note and invoice. Detail JSON may use a plural root.
Allocation is not a cash refund. The approved narrow ownership exception permits
allocation affecting only the selected existing issued credit and invoice, after
complete reads, exact preview and separate approval. It excludes invoice edits,
cash refunds and unrelated records; it never supplies issuance approval. Preserve provider
errors and inspect uncertain writes before any retry.


## Recurring invoices (read-only)

- The [documented recurring invoice API](https://dev.freeagent.com/docs/recurring_invoices)
  offers collection/detail GETs and view/contact filters, not profile creation.
- Inactive is a collection view; documented recurring_status values are Active and
  Draft. Preserve view evidence separately from provider status fields.
- next_recurs_on and recurring_end_date are provider billing information, not cash
  receipt predictions. Missing dates or values stay unavailable, never generated.
- No generated-invoice/profile link is documented. Do not match records or compute
  overlap. Use [named profile reads](recurring-revenue.md) without custom calculations.

## Document PDFs

Provider PDF endpoints for invoices, estimates and credit notes return RFC 2045 base64 at `pdf.content`. Hosted named reads verify record identity and PDF bounds, then emit public metadata plus a private original-bound UI context. Its authenticated UI-only refresh mints a short one-file delegated capability; the browser route auto-submits for a native HTTPS attachment without cookie or login dependence. Legacy local embedded resources remain diagnostics only; installed web/mobile delivery acceptance remains separate. See [document transport](documents.md) for limits and client verification gates.

## Payroll reads

The [payroll API](https://dev.freeagent.com/docs/payroll) requires UK payroll
support and Tax and Limited Accounting access. Year is the tax-year end, and
period identifiers come from the provider. Annual periods and payments are
separate collections; period details omit payslips for privacy. See
[payroll evidence](payroll.md) for missing-state, currency and filing/payment
limitations. No mark-paid/unpaid or other payroll transition is exposed.
