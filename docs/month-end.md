# Month-end evidence coverage

The [month-end workflow](../.agents/skills/month-end/SKILL.md) reviews current
FreeAgent records dated in a user-selected period. It is read only and does not
certify the books, reconstruct historical status or implement accounting rules.

| Evidence | Named hosted reads | Scope and limits |
| --- | --- | --- |
| Company and accounts | `get_company`, `list_bank_accounts` | Confirm company and selected account IDs before collecting data. |
| Unexplained transactions | `list_bank_transactions` | bank_account, view=unexplained, from_date/to_date; preserve unexplained_amount and source URLs. Transaction amount is in the company's native currency; only label currency from confirmed provider context. |
| Overdue bills | `list_bills` | view=overdue, from_date/to_date and optional contact. |
| Overdue and draft invoices | `list_invoices` | Separate view=overdue/draft calls; optional contact/project. No invoice date query exists here; select displayed dated_on records from complete results. Missing dates remain unknown. |
| Unbilled time | `list_timeslips` | view=unbilled, from_date/to_date and optional project; retain billed_on_invoice and timer evidence without calculating eligibility or totals. |
| Receipt and possible duplicate review | `list_expenses`, `list_bills` and matching detail reads | Full period collections, not just overdue bills. Return attachment metadata and receipt references unchanged. Missing attachment data is unknown; comparisons are uncertain suggestions, never duplicate determinations. |

List and detail responses for these resource types include collected_at, a server
UTC read-completion timestamp added after successful provider retrieval/projection.
It is transport metadata, not a provider accounting date or atomic snapshot.
Linked pages aggregate once by default. Any page error fails the read; a denied,
malformed or incomplete collection cannot become an empty successful review.

Order follow-up suggestions by the workflow above, cite the provider record and
reason, and ask the user which action they want. Existing bank-reconcile,
invoice-status, bills, invoicing, timesheets, receipts and expenses workflows own
any subsequent exact preview, approval, ownership and readback. Re-read the
original-company records after the selected action; uncertain results need
inspection, never an automatic replay. This review neither sends chasers nor
changes existing accounting records.

Tests use synthetic authenticated HTTP fixtures to verify named tool discovery,
provider requests, pagination, projection and failures. Static workflow assertions
check the explanation/handoff contract. They do not prove observed assistant
behavior, live FreeAgent results or marketplace-installed web/iOS delivery; those
remain separate verification gates.

Provider contracts: [bank transactions](https://dev.freeagent.com/docs/bank_transactions),
[timeslips](https://dev.freeagent.com/docs/timeslips),
[invoices](https://dev.freeagent.com/docs/invoices),
[bills](https://dev.freeagent.com/docs/bills), and
[expenses](https://dev.freeagent.com/docs/expenses).
