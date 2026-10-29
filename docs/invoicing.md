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
accounting calculations and duplicate billing prevention. Delivery is a separate
approval-controlled workflow below. Existing `create_draft_invoice` retains its
original timeslip convenience behavior.

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

## Approved invoice delivery and duplication policy

The user authorized implementation of this narrow scope on 2026-10-29. This
policy extends draft-only creation with separately approved named operations;
it does not authorize a live write or email without the exact per-action approval.
Generic local API access and OAuth write scope do not override agent policy.

### Provider mechanics considered

Checked 2026-10-29 against the [provider invoice contract](https://dev.freeagent.com/docs/invoices):

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

### Approved first scope

Enable one selected invoice at a time: duplicate into a new Draft, mark a
current-request-created Draft as sent, or explicitly email that created invoice.
Keep scheduling, cancellation/write-off, reopening, reverting existing documents,
payment collection, marking paid, refunds, bulk delivery and automatic reminders
outside this first scope. Do not pass arbitrary transition names through a tool.
FreeAgent decides supported transitions and accounting validity; do not reproduce
its state machine or calculate balances/tax locally.

Duplication is a narrow exception allowing a selected existing invoice
to be a read-only source for a separately approved new Draft. It does not grant
ownership of the source. Existing invoices remain ineligible for sending or status
changes under this policy: prepare review material and let the user act in
FreeAgent instead. A duplicate's returned URL establishes its current-request
creation only after verified readback. Creating a duplicate does not authorize
sending it, changing the original, or duplicating again after an uncertain result.

### Review and approval sequence

1. Establish the active linked company and selected invoice using the existing
   named reads. Inspect complete contact/project/invoice evidence, prior drafts
   and relevant duplicate candidates across all pages. Record source identity,
   request ownership, provider status, reference, lines, currency, totals and all
   three automatic-email flags. Missing or denied coverage is unavailable, not an
   empty collection. Stop for conflicting changes, ambiguous records or unsupported
   ownership; ask for missing business inputs rather than guessing.
2. For duplication, preview the exact source, the new-Draft intent and provider
   date/reference behavior. Require explicit approval for this creation alone.
   Call `duplicate_invoice` only after that approval. It reads back the new Draft,
   original source and automatic email flags. Stop before any delivery if flags
   are not verified off. Do not
   promise duplication suppresses inherited settings without provider evidence.
3. For a status transition, preview the exact owned invoice, current provider
   state and requested named transition. Explain that marking sent changes its
   accounting state and is distinct from emailing it. Verify automatic email
   settings are off before offering that operation, so an unreviewed template is
   not triggered. Require explicit transition approval separate from draft approval.
   Call `mark_invoice_as_sent` once, then inspect the returned status and settings
   before considering delivery. Do not infer from documentation whether a particular
   account permits the transition.
4. For email, preview the exact company and invoice, recipients, registered-user
   sender, subject, full message, sender-copy choice, rebilled receipt inclusion,
   every attachment's identity/type/size and all automatic-email settings. Confirm
   recipient spelling and resolve recipient/contact discrepancies with the user.
   Do not invent addresses, CC/BCC fields, template wording or defaults. The named
   email operation accepts explicit reviewed `to`, `from`, `subject`,
   `body` and `email_to_sender`; all are required, with no guessed defaults. It
   fixes `attach_expense_receipts` to false, accepts no extra attachments and does
   not use template mode. Requests needing templates or attachments remain
   unsupported; ask the user to send those in FreeAgent. No recipient data or
   message content is included in tool errors.
5. Review the selected document through the available authenticated document
   workflow. If its client route is unavailable, have the user review the exact
   invoice in FreeAgent and confirm its identity/content before returning for
   the separate send approval. Missing document review blocks delivery. Never
   substitute a guessed local path or public download URL. If the invoice, PDF,
   recipients or settings change after approval, refresh the preview and obtain
   approval again.
6. Obtain a clear approval to **send this exact email now**, separate from draft,
   duplicate and status approvals. A request to chase an invoice or approval of
   draft text is not sending approval. A refusal or missing approval means no call.
   Call `send_invoice_email` with numeric `id`, exact reviewed `email` fields and
   `confirmed: true`. All three named actions require write scope and confirmation;
   agents remain responsible for ownership, exact scope and user approval.
7. Submit each approved action once. After emailing, the helper reads the selected
   invoice and returns `request_accepted: true` and `recipient_delivery: unavailable`
   alongside its provider state. These are transport evidence and an explicit
   limitation, not a provider delivery receipt. Label unknown recipient delivery
   explicitly. A successful status transition does not establish email delivery, and a successful
   email response does not establish recipient receipt or payment.
8. On rejection, timeout, disconnect or failed readback, report the exact attempted
   action and original company/invoice, and whether the outcome is uncertain or
   only partially verified. Inspect the original record and available provider
   evidence before any further action. Do not automatically replay email, repeat
   duplication or treat unchanged invoice status as proof that no email was sent.
   If the provider cannot establish whether an email was accepted, stop and ask
   the user to inspect FreeAgent; no blind retry or retry-on-approval shortcut.

The invoice-status workflow remains read-only, including drafting chasers. This
policy does not turn it into a sending workflow or expand the existing
credit-allocation exception.

### API mechanics and verification

The three operations use only the fixed documented endpoints above. Duplication
reads back the new returned invoice and original source; status/email actions read
back the selected invoice. Unknown duplicate identities, malformed results and
failed readbacks report incomplete/uncertain verification rather than success.
No write is automatically retried. HTTP errors expose only status and selected
record identity, never recipient/message bodies echoed by a provider error.
Accounting and address validation remain FreeAgent's responsibility; the server
has no ownership ledger, state machine, duplicate accounting engine or calculated
balance. The agents must refuse historical-invoice delivery/status changes under
this policy even though the transport cannot independently know request ownership.

Synthetic authenticated HTTP tests cover generated skills/discovery/audit, exact
provider payloads, approved duplication/transition/email readbacks, denied scope,
refusal, unsupported templates/attachments, provider rejection, timeouts and
partial readback failures. They establish API mechanics, not observed assistant
approval decisions or live delivery. Authorized sandbox verification, independent
financial/security review and installed web/mobile behavior remain release gates.
Do not claim recipient receipt, delivery or payment from invoice status or a
successful API email request. No live financial/email write is made by these tests.
