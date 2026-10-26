# Provider-backed draft invoice creation

Contract checked 2026-10-26 against [invoices](https://dev.freeagent.com/docs/invoices)
[estimates](https://dev.freeagent.com/docs/estimates),
[bills](https://dev.freeagent.com/docs/bills) and
[bank explanations](https://dev.freeagent.com/docs/bank_transaction_explanations).

`create_draft_invoice_from_payload` takes one `invoice` object and posts it to the
fixed invoices endpoint, then reads the created resource. Full resource URLs inside
that object and all manual line fields, explicit zero/empty values, currency and
inclusion strings pass through. Its intentional convenience defaults overwrite
`status` with Draft and the three automatic email flags with false. FreeAgent
creates Draft invoices and owns field validation, accepted source eligibility,
accounting calculations and duplicate billing prevention. No issuing/sending
operation is added. Existing `create_draft_invoice` retains its original timeslip
convenience behavior.

Supported documented inclusion values:

| Field | Values other than null | Provider scope |
| --- | --- | --- |
| include_timeslips | billed_grouped_by_single_timeslip, billed_grouped_by_timeslip, billed_grouped_by_timeslip_task, billed_grouped_by_timeslip_date | Project time |
| include_estimates | billed_grouped_by_single_estimate, billed_grouped_by_estimate | Open/approved estimates |
| include_expenses | billed_grouped_by_single_expense, billed_grouped_by_expense | Expenses, bills and bank account entries |

These values are forwarded, not locally enumerated or validated. A provider mode
is not an individual source-ID selector. The agent must inspect the entire eligible
scope and obtain approval; if provider reads do not establish the scope, it must
stop rather than promise selected records only. Approved estimate state is not
permission to create an invoice. Placeholder lines plus included sources can add
unexpected items: do not invent placeholders. Provider rejection is evidence,
not permission to bypass a validation rule.

Bill `rebilled_on_invoice_item` is preserved exactly as returned (including the
provider documentation's invoice URL example); do not infer a different relationship
from its name. Bank-explanation project/rebill/tax fields are retained to inspect
bank entries that provider expense inclusion may also include. Missing links stay
unknown; no source relationship is manufactured.

The remote workflow uses list/get contacts, projects, invoices, estimates,
expenses, bills, timeslips and bank records as needed. The named create tool accepts
nested provider objects without client Python or a generic executor. Review exact
inputs and provider-returned evidence; unsupported pre-write totals remain unavailable.
After creation verify provider status, emails, currency, totals, invoice items and
available source links; reread sources and report missing/unexpected fields. No
local invoice, tax, currency or balance calculation is provided. Inspect uncertain
writes or failed readback before retrying.

Synthetic authenticated HTTP tests prove package discovery, fixed transport,
unchanged provider inputs/returned values, scope/approval denial and failure
handling. They do not prove provider accounting rules, sandbox source inclusion,
actual assistant decisions or deployed marketplace-installed web/iOS behavior.
Those live evidence gates remain separate; no financial writes are made by tests.
