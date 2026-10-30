# Credit-note workflow and allocation policy

Provider contracts checked 2026-10-25: [credit notes](https://dev.freeagent.com/docs/credit_notes)
and [reconciliations](https://dev.freeagent.com/docs/credit_note_reconciliations).

## API mechanics

`create_draft_credit_note` posts root credit_note to credit_notes, with contact,
dated_on, payment_terms_in_days and credit_note_items. Optional project, currency
and reference are forwarded. FreeAgent always creates Draft; the helper does not
send status, issue, email or allocate. Signed item fields pass through unchanged;
the provider, not a local validator, decides accepted signs, taxes and relationships.
Readback preserves item lines, signed totals, currency/exchange rate, terms,
status and due/refunded values. Missing fields never mean zero.

`create_credit_note_reconciliation` posts root credit_note_reconciliation with
credit_note, invoice, gross_value and optional dated_on/currency/exchange_rate.
It reads the created reconciliation, credit note and invoice, returning all three.
The provider's GET detail example has a plural credit_note_reconciliations root;
both singular and plural roots are normalized. Allocation is not a cash refund.
Read/create tools are mechanics, not authorization to bypass the workflow policy.
Hosted top-level reference inputs are numeric IDs; item payloads retain documented
provider fields and resource URLs. Generic local tools remain unchanged.

## Approved narrow allocation policy

The user approved a narrow exception to current-request ownership on 2026-10-25.
The exception permits only a new reconciliation affecting a specifically selected
existing issued credit note and existing invoice. It does not authorize invoice
edits, credit issuing/status changes, sending/email, cash refunds, unrelated record
changes or mutation of old reconciliations. All other ownership restrictions remain.

Before allocation, read the original linked company, selected credit and invoice,
all related credits/reconciliations and current currency/balance evidence. Resolve
duplicates and unavailable evidence before action. Preview both identities, exact
amount/date/currency/exchange-rate basis, provider-returned current balances and
provider-returned or explicitly user-supplied expected resulting balances, each
labelled with its source. Never calculate expected balances, totals, tax or currency
conversions. An unavailable provider expectation remains unavailable; user-supplied
expectations are not provider-verified accounting results. Obtain separate approval
of that allocation, submit once and read back
reconciliation, credit and invoice. Report provider-returned remaining/unapplied
values and
partial failures; inspect an uncertain result before any retry, never replay blindly.
FreeAgent decides accounting eligibility, signs and over-allocation. Missing fields
are unknown; do not invent balances or exchange rates.

Issuance and allocation are separate actions. The allocation exception does not
itself authorize issuing a Draft. A Draft created in the current user request may
be issued only under the issuance policy below with separate exact approval.
Older Drafts remain excluded. The approved allocation exception is shared in
[agent rules](agent-rules.md#approved-credit-allocation-exception).

## Current-request Draft issuance policy

`issue_credit_note` is the fixed hosted status-transition operation. It requires
write scope and `confirmed=true`, submits one transition and reads the credit
back in the same account binding. Ownership and exact approval are agent
responsibilities, not a server ledger. This source implementation and policy are
subject to independent review and human PR merge; no live financial action is
authorized by implementing the feature.

The [provider credit-note contract](https://dev.freeagent.com/docs/credit_notes)
was checked on 2026-10-29. It documents
`PUT credit_notes/:id/transitions/mark_as_sent`, returning HTTP 200, separately
from `POST credit_notes/:id/send_email`. The transition can also reopen a
cancelled credit; that broader provider behavior is outside this workflow.
Provider status values include `Draft`, `Open`, `Overdue`, `Refunded` and
`Written-off`; do not expect a literal `Sent` readback merely because of the
transition's name. Sandbox verification of actual eligible transitions remains
a separate release-evidence gate.

This workflow permits only a Draft created and successfully read back
during the current user request, in the same linked company. It does not grant
ownership over an older Draft, reopen a cancelled credit, return an issued credit
to Draft, edit invoice lines, send email, cancel a credit or refund cash. Existing
issued credits remain eligible only for the separately approved allocation
exception above. No additional exception for historical drafts is proposed.

The agent must follow these steps:

1. Establish current-request creation evidence and re-read the company, selected
   Draft, original invoice where applicable, and complete related credit and
   reconciliation collections. Stop on an incomplete read, unresolved duplicate,
   changed company, changed document or unavailable ownership evidence. Provider
   eligibility remains FreeAgent's decision; do not build a local accounting engine.
2. Preview the company, credit identity/reference, contact/project, source invoice,
   date, signed lines/tax, currency/exchange-rate basis and all provider-returned
   totals/balances. Label missing values unavailable. Explain the exact status
   transition and that it neither emails the customer nor allocates credit or
   pays cash. Do not invent expected totals, balances or conversions.
3. Obtain separate explicit approval to issue that exact Draft. Draft-creation
   approval, policy acceptance, allocation approval and a general request to
   process credits are insufficient. Refusal causes no write. If the record
   changes after preview, refresh the preview and obtain approval again.
4. Submit the fixed status transition once. Read back the credit, source invoice
   where applicable and related reconciliations in the original company. Report
   actual returned status, lines, totals, balances and relationships; flag changes
   or missing evidence. HTTP 200 alone is not verification. An unexpected state
   blocks further action; do not force a preferred status or manufacture balances.
5. On timeout, denial, provider rejection or failed readback, report the outcome
   and re-read the original records before considering any further write. Do not
   automatically retry the transition, recreate the credit, email it or allocate
   it as a workaround. If status is already issued, do not replay issuance. Any
   retry after evidence establishes no transition requires a fresh exact approval.
6. Allocation, if requested after verified issuance, still requires the full
   existing allocation preview, eligibility/duplicate reads and separate exact
   approval. Issuance approval never authorizes allocation.

Independent financial-workflow review must assess the ownership boundary,
refusal and uncertain-result paths. Synthetic authenticated tests verify discovery,
write authorization, fixed provider requests and credit readbacks. The agent also
re-reads source invoice and complete related reconciliations where applicable;
issuance itself neither allocates credit nor edits an invoice. Sandbox acceptance
and actual installed web/mobile behavior remain separate evidence gates.

## Review examples and safeguards

These are policy review examples, not claims of observed assistant execution:

- Selected existing issued credit + existing invoice, complete duplicate/balance
  reads and separate exact approval: allocate once and compare all three provider readbacks with the sourced preview.
- Current-request Draft: leave Draft unless a separate exact issuance preview is
  approved. Older Draft or unavailable creation evidence: do not issue.
- User refuses allocation or only approves draft creation: no allocation write.
- Missing currency/balance/duplicate coverage: stop before proposing a verified
  result; obtain missing evidence instead of treating it as zero.
- Partial/full or foreign-currency allocation: preserve the provider's accepted
  signs and currency basis; over-allocation rejection is reported without replay.
- Created reconciliation but invoice readback fails: report partial verification,
  inspect all original records and do not apply the amount a second time.

## Evidence and release limits

Synthetic dispatcher tests exercise partial/full and foreign-currency requests,
provider over-allocation rejection, approval refusal, duplicate-review reads,
timeouts and failed readbacks, including affected invoice/credit reads. They prove
transport mechanics, not provider accounting rules or assistant decisions.
Use the skill's source-evidence preview for duplicate proposals; no server ledger or
local duplicate-accounting validator is introduced. Independent financial-workflow
review is required before PR readiness. Authorized provider sandbox acceptance and
real account eligibility remain external release gates; no live writes are implied.

## Marketplace runtime audit

The installed ChatGPT web/iOS workflow uses conversational review and the remote
named tools in its skill. Contact/invoice/credit/reconciliation reads and creation, issuance and allocation operations are declared in the hosted registry and exposed through authenticated
MCP discovery/invocation. The package includes this document, the skill and shared
agent rules with source digests. It requires no client-local Python, shell, files,
CLI or generic API executor. Python helpers described above execute inside the
remote service; their presence alone is not evidence of client availability.
Synthetic authenticated HTTP tests discover named operations and invoke them
through tools/call with the real dispatcher, including affected-record readback.
This proves the packaged route and server mechanics, not publication, installed
ChatGPT web/iOS execution or deployed provider availability; those require actual
marketplace installation and authorized end-to-end verification.
