# Credit-note workflow and policy gate

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

## Current policy and decision required

The current ownership restriction remains in force: do not change records created
outside the current user request. Invoice allocation affects an existing invoice's
balance even though the reconciliation is a new resource. Thus ordinary allocations
to historical invoices are not authorized by adding a create tool. The credit-note
workflow stops before issuing or allocating until an explicit policy review.
No issuing/status-transition/email operation is added here.

A proposed future decision for human review (NOT active policy): permit a separately
approved reconciliation against an explicitly selected pre-existing invoice after
reading its current state, all related credits/reconciliations and currency basis;
preview both record identities, exact amount/date/currency and expected balances;
obtain separate approval, write once and read all affected records. Restrict the
exception to allocation, not invoice edits, issuing or cash refunds. Define whether
same-request credit issuance is authorized separately. Until that decision is
approved, retain current restrictions and explain the blocked action to the user.
An implementation review or PR merge does not itself approve this future policy.

## Evidence and release limits

Synthetic dispatcher tests exercise partial/full and foreign-currency requests,
provider over-allocation rejection, approval refusal, duplicate-review reads,
timeouts and failed readbacks, including affected invoice/credit reads. They prove
transport mechanics, not provider accounting rules or assistant decisions.
Use the skill's source-evidence preview for duplicate proposals; no server ledger or
local duplicate-accounting validator is introduced. Independent financial-workflow
review is required before PR readiness. Authorized provider sandbox acceptance and
real account eligibility remain external release gates; no live writes are implied.
