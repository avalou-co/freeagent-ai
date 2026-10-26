# Hosted API inventory and design contract

Checked against FreeAgent documentation on 2026-10-12. `public_tools.audit()` exports
every fixed endpoint, JSON schema, permission and annotation for review and CI.
The local generic tools continue unchanged. The public dispatcher never receives
an arbitrary API destination/method and does not reproduce accounting validation.

| Resources | Public operations | Provider source |
| --- | --- | --- |
| Contacts | list/get/create/update/delete | https://dev.freeagent.com/docs/contacts |
| Projects | list/get/create/update/delete | https://dev.freeagent.com/docs/projects |
| Tasks | list/get/create/update | https://dev.freeagent.com/docs/tasks |
| Timeslips | list/get/create/update/delete | https://dev.freeagent.com/docs/timeslips |
| Invoices | list/get/create draft/update/delete | https://dev.freeagent.com/docs/invoices |
| Credit notes | list/get/create draft; signed values, refund and item context | https://dev.freeagent.com/docs/credit_notes |
| Credit-note reconciliations | list/get/create; affected credit/invoice readback, separately approved narrow allocation | https://dev.freeagent.com/docs/credit_note_reconciliations |
| Expenses | list/get/create/update/delete; create_expense_from_payload forwards exact tax fields; reads retain receipt reference and original/native/manual tax evidence | https://dev.freeagent.com/docs/expenses |
| Mileage expenses | get_mileage_settings/create_mileage_expense; list/get use expenses and retain mileage/engine/reclaim fields | https://dev.freeagent.com/docs/expenses |
| Estimates | list/get/create draft/update/delete | https://dev.freeagent.com/docs/estimates |
| Bills | list/get/create/update/delete | https://dev.freeagent.com/docs/bills |
| Bank accounts/transactions | list/get | https://dev.freeagent.com/docs/bank_accounts and https://dev.freeagent.com/docs/bank_transactions |
| Bank explanations | get/create/delete; safe legacy/plural attachment references | https://dev.freeagent.com/docs/bank_transaction_explanations |
| Bank-explanation attachments | list/add one/update one/remove one; automatic collection readback after writes | https://dev.freeagent.com/docs/bank_transaction_explanation_attachments?version=2026-09-01 |
| Users/company/categories | list/get, current-user/company | https://dev.freeagent.com/docs/users and https://dev.freeagent.com/docs/company and https://dev.freeagent.com/docs/categories |
| Tax returns | VAT, Corporation Tax and user-scoped self-assessment list/get only | https://dev.freeagent.com/docs/vat_returns and https://dev.freeagent.com/docs/corporation_tax_returns and https://dev.freeagent.com/docs/income_tax_returns |
| Accounting reports | P&L summary, balance sheet, trial balance summary | https://dev.freeagent.com/docs/profit_and_loss and https://dev.freeagent.com/docs/balance_sheet and https://dev.freeagent.com/docs/trial_balance |

Task DELETE is intentionally unavailable: the provider's task-deletion section
currently prints a users/:id endpoint. Request provider clarification rather than
infer a potentially destructive endpoint. Bank-explanation updates and arbitrary
status/send transitions are not exposed; no documented operation is invented.
Use the supported correction or explain the missing operation to the user.

Named helpers preserve existing Draft defaults and automatic-email disabling.
Updates send the exact provider payload unchanged and are annotated destructive;
invoice update is open-world because its email settings may affect recipients.
Bank explanation is destructive. Bounded private reads/other writes are not
open-world merely because FreeAgent is externally hosted.

Response projections contain workflow accounting fields and necessary provider
references. Signed attachment URLs/content, user email/profile details, account
numbers, authentication, debug data and timestamps are not echoed by default.
Provider-defined accounting report totals/rows are projected separately. Validate
schemas against sample accounts; mocked responses do not prove provider behavior.
For a requested field absent from the projection, say so rather than infer it.

Approval and current-request ownership remain agent responsibilities. Every public
write also requires confirmed=true as the agent's assertion; it is not independent
proof of approval. No task ledger, billing reservation or local eligibility locks
are introduced. Local generic payloads/responses remain direct API mechanics.

Analysis projection coverage, required fields, incomplete-data behavior and provider
verification limits are audited in [the hosted coverage table](analysis.md#hosted-field-coverage).

Bank API requests explicitly opt into `X-Api-Version: 2026-09-01`; see the
[attachment migration](bank-attachments.md). Named attachment operations accept an
explanation numeric `id`, and update/remove also take numeric `attachment_id`.
`add_bank_transaction_explanation_attachment` requires a `file` reference;
`update_bank_transaction_explanation_attachment` accepts optional `file` and
`description` (including an explicit empty description). Both file-bearing tools
publish `openai/fileParams`. Removal uses the provider's PUT `_destroy`, not an
invented DELETE-item path. A bulk delete-all tool is intentionally absent: each
existing attachment requires current-request ownership and exact approval.

Attachment validation errors expose status only because provider bodies can echo
file contents. Safe collection projections return `url`, `file_name`, `content_type`,
`file_size`, `description`; signed content/thumbnail URLs and bytes never enter
hosted results. An unavailable/malformed read is incomplete, never an empty list.
Local generic calls remain direct API mechanics and can return raw provider
attachment data; agents must not print signed URLs or content.

Tax payment projection, permission and partial-balance limits are documented in
[tax evidence rules](tax-overview.md). Date-addressed return details use period_ends_on;
no filing or payment transitions are exposed.

Credit-note creation/allocation mechanics and the approved narrow ownership exception are documented in [credit policy](credit-notes.md). Allocation may affect only the selected existing issued credit/invoice after exact preview and separate approval. Issuing, invoice edits and cash refunds remain excluded; other ownership restrictions remain active.


## Recurring invoice reads

`list_recurring_invoices` and `get_recurring_invoice` are fixed read-only operations
from the [provider contract](https://dev.freeagent.com/docs/recurring_invoices),
checked 2026-10-26. Collection filters are view and contact; pagination and numeric
contact expansion use shared API mechanics. Safe projections preserve returned
profile identity, contact/project, frequency, recurring_status, next/end dates,
currency, values, payment terms and line items; absent fields remain absent.
Both result envelopes add collected_at (UTC read-completion time, not a provider
record-change date or an atomic multi-page snapshot).

The [recurring profile workflow](recurring-revenue.md) uses the active/inactive/draft
views and explains only provider results. No profile mutation, future-date expansion,
payment/cash forecast, custom calculation tool, local runtime or undocumented
invoice/profile relationship is introduced. The generated audit derives both GET
operations from the registry. Unsupported provider capabilities remain unavailable.


## Exact expense payloads

`create_expense_from_payload` is a fixed `POST expenses` operation followed by
`GET` of the created expense. The `expense` object retains the exact approved
provider fields, decimal strings, empty/zero values and full provider resource
URLs; FreeAgent validates tax/accounting combinations. It requires write scope
and `confirmed=true`. Optional `receipt` uses the bounded ChatGPT file-reference
contract, never a local path or embedded attachment bytes. Readbacks project
documented original/native/manual and secondary-tax evidence and safe attachment
metadata; missing fields remain unknown. See [receipt semantics](receipts.md).

Synthetic tests verify generated skills, remote discovery, authenticated HTTP
provider requests and readbacks. These do not prove provider tax acceptance,
assistant decisions, deployed account isolation or installed web/iOS behavior.
