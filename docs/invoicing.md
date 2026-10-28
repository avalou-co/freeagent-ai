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

## Proposed delivery policy — pending human acceptance

This is the reviewable product-policy prerequisite for
[#73](https://github.com/avalou-co/freeagent-ai/issues/73), not permission to send,
duplicate or transition an invoice. Current draft-only/no-send and current-request
ownership rules remain in force. No delivery, duplication or transition tool is
added here. Human acceptance of the policy and separate implementation/review are
required before enabling any of these actions. Generic local API access and an
OAuth write scope do not override agent policy.

### Provider mechanics considered

Checked 2026-10-28 against the [provider invoice contract](https://dev.freeagent.com/docs/invoices):

- `POST invoices/:id/duplicate` returns a new Draft with today's date and the next
  global reference. Verify actual returned values; do not predict them.
- `POST invoices/:id/send_email` accepts `invoice.email`: `to`, registered-user
  `from`, `subject`, `body`, `email_to_sender`, `attach_expense_receipts` and
  attachments (`file_name`, `content_type`, base64 `data`, up to 5 MB each).
  `use_template: true` selects the existing template. Sender-copy defaults to true.
- Separate PUT transitions include `mark_as_sent`, `mark_as_scheduled`,
  `mark_as_draft` and `mark_as_cancelled`. Updating ordinary invoice fields is not
  a status transition. Mark-as-sent can reopen a cancelled invoice; cancellation
  writes off a past-due sent invoice.
- Email success is HTTP 200. Invoice status is accounting state, not recipient
  delivery confirmation. Do not assume an email-receipt, delivery log or preview
  endpoint exists.

### Proposed first scope

Enable one selected invoice at a time: duplicate into a new Draft, mark a
current-request-created Draft as sent, or explicitly email that created invoice.
Keep scheduling, cancellation/write-off, reopening, reverting existing documents,
payment collection, marking paid, refunds, bulk delivery and automatic reminders
outside this first scope. Do not pass arbitrary transition names through a tool.
FreeAgent decides supported transitions and accounting validity; do not reproduce
its state machine or calculate balances/tax locally.

Duplication would be a narrow new exception allowing a selected existing invoice
to be a read-only source for a separately approved new Draft. It would not grant
ownership of the source. Existing invoices remain ineligible for sending or status
changes under this proposal: prepare review material and let the user act in
FreeAgent instead. A duplicate's returned URL establishes its current-request
creation only after verified readback. Creating a duplicate does not authorize
sending it, changing the original, or duplicating again after an uncertain result.

### Proposed review and approval sequence

1. Establish the active linked company and selected invoice using the existing
   named reads. Inspect complete contact/project/invoice evidence, prior drafts
   and relevant duplicate candidates across all pages. Record source identity,
   request ownership, provider status, reference, lines, currency, totals and all
   three automatic-email flags. Missing or denied coverage is unavailable, not an
   empty collection. Stop for conflicting changes, ambiguous records or unsupported
   ownership; ask for missing business inputs rather than guessing.
2. For duplication, preview the exact source, the new-Draft intent and provider
   date/reference behavior. Require explicit approval for this creation alone.
   The future helper must read back the new Draft, original source and automatic
   email flags. Stop before any delivery if flags are not verified off. Do not
   promise duplication suppresses inherited settings without provider evidence.
3. For a status transition, preview the exact owned invoice, current provider
   state and requested named transition. Explain that marking sent changes its
   accounting state and is distinct from emailing it. Verify automatic email
   settings are off before offering that operation, so an unreviewed template is
   not triggered. Require explicit transition approval separate from draft approval;
   read back status and settings before considering delivery. Do not infer from
   documentation whether a particular account permits the transition.
4. For email, preview the exact company and invoice, recipients, registered-user
   sender, subject, full message, sender-copy choice, rebilled receipt inclusion,
   every attachment's identity/type/size and all automatic-email settings. Confirm
   recipient spelling and resolve recipient/contact discrepancies with the user.
   Do not invent addresses, CC/BCC fields, template wording or defaults. The first
   implementation should use explicit reviewed email fields, no extra attachments
   or rebilled receipts, and no unresolved template mode. Future attachment or
   template support needs a separate bounded transport and content-review design.
5. Where document retrieval from #72 is available, review the authenticated PDF
   associated with the selected invoice before delivery. Treat unavailable PDF
   rendering as a failed document-review prerequisite; direct the user to FreeAgent
   for review instead. Never substitute a guessed local path or public download
   URL. If the invoice, PDF, recipients or settings change after approval, refresh
   the preview and obtain approval again.
6. Obtain a clear approval to **send this exact email now**, separate from draft,
   duplicate and status approvals. A request to chase an invoice or approval of
   draft text is not sending approval. A refusal or missing approval means no call.
   The future named remote tool must require write scope and `confirmed: true`;
   agents remain responsible for ownership, exact scope and user approval.
7. Submit each approved action once. After emailing, read the selected invoice
   and report the provider response, status/settings and any documented delivery
   evidence actually available. Label unknown recipient delivery explicitly. A
   successful status transition does not establish email delivery, and a successful
   email response does not establish recipient receipt or payment.
8. On rejection, timeout, disconnect or failed readback, report the exact attempted
   action and original company/invoice, and whether the outcome is uncertain or
   only partially verified. Inspect the original record and available provider
   evidence before any further action. Do not automatically replay email, repeat
   duplication or treat unchanged invoice status as proof that no email was sent.
   If the provider cannot establish whether an email was accepted, stop and ask
   the user to inspect FreeAgent; no blind retry or retry-on-approval shortcut.

The invoice-status workflow remains read-only, including drafting chasers. This
proposal does not turn it into a sending workflow or expand the existing
credit-allocation exception.

### Acceptance and evidence still required

Before runtime implementation, obtain human acceptance of this exact scope and
ownership exception. Then independently review fixed named operations, approval
annotations, readback/uncertain-outcome handling, privacy and authenticated package
coverage. Use synthetic cases for refused sends, recipient discrepancies, invalid
provider transitions, existing-record refusal, duplicate proposals, partial failures
and timeouts. Do not implement a local accounting/eligibility engine or server task
ledger. Future delivery tests must establish actual provider request/response
mechanics; conversational decisions require separate observed assistant evidence.

The current regression tests establish that named sending, duplication and
transition operations are absent from the generated audit and authenticated MCP
discovery, and cannot reach the provider even with write scope and confirmation.
They do not establish a delivery feature. Authorized sandbox verification, #72
document viewing and actual installed web/iOS behavior remain external release
gates. No live financial or email write is authorized by this policy proposal.
