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
amount/date/currency/exchange-rate basis, current balances and expected resulting
balances. Obtain separate approval of that allocation, submit once and read back
reconciliation, credit and invoice. Report actual remaining/unapplied values and
partial failures; inspect an uncertain result before any retry, never replay blindly.
FreeAgent decides accounting eligibility, signs and over-allocation. Missing fields
are unknown; do not invent balances or exchange rates.

A newly created Draft remains Draft. This policy does NOT authorize issuing it to
make it allocatable. Use a provider-eligible existing issued credit for allocation;
if none exists, prepare the draft and explain that issuance needs a separate future
policy decision. No issuance/status-transition/email operation is added. Draft
approval and this policy approval do not substitute for exact per-allocation approval.
The approved exception is shared in [agent rules](agent-rules.md#approved-credit-allocation-exception).

## Review examples and safeguards

These are policy review examples, not claims of observed assistant execution:

- Selected existing issued credit + existing invoice, complete duplicate/balance
  reads and separate exact approval: allocate once and compare all three readbacks.
- Draft credit, even created and approved in the same request: leave Draft, explain
  issuance is unavailable, do not call a transition or allocate it to bypass issuance.
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
