---
name: credit-notes
description: Review customer credits, create draft credit notes, separately approve current-request Draft issuance and prepare invoice allocations under the reviewed ownership policy.
---

# Credit notes

Follow [agent rules](../../../docs/agent-rules.md) and [credit policy](../../../docs/credit-notes.md).
Ask for the company, contact, invoice, reason, date, reference, terms, currency and
exact signed line quantities/prices/tax. Show only provider-returned or explicitly
user-supplied financial values; never compute totals, balances, tax or conversions.
Never assume a full refund, tax rate or exchange rate.

1. Resolve contact and invoice with reads. List all related credits including Draft,
   and all reconciliations (filter the complete collection by returned URLs). Read
   candidate details and source invoice lines. An incomplete/denied read blocks a
   duplicate conclusion and creation. A similar draft may already fulfil the request;
   show evidence and ask the user to resolve it rather than create another.
2. Preview contact/project, original invoice, exact signed lines, tax, currency,
   provider-returned or user-supplied net/tax/gross totals, reference/terms and potential duplicates. Distinguish invoice
   credit allocation from cash refund. No status or sending action is implied.
3. Obtain approval of this exact draft. If refused, stop without any write. Use
   `create_draft_credit_note` once, then verify provider Draft status, reference,
   contact, currency, every line and totals. Never treat a POST response as readback.
   Report any changed or absent provider values and leave the credit unissued.
4. Issue only a Draft created and successfully read back during this user request,
   in the original company. Read company, credit, source invoice where applicable
   and complete related credits/reconciliations. Stop for unavailable ownership,
   incomplete reads, unresolved duplicates or changed records. Preview exact credit
   identity/reference, contact/project, signed lines/tax, date, currency/exchange-rate
   basis and provider totals/balances. Obtain separate explicit issuance approval;
   draft approval is insufficient. If refused, do not write. Use `issue_credit_note`
   once, then verify the returned credit status/lines/balances and re-read source
   invoice and related reconciliations where applicable. Report unexpected or absent
   values; a success status alone does not prove verification. Never issue an older
   Draft, reopen a cancelled credit or assume the provider returns literal Sent.
   Issuance does not email, allocate or refund. Allocation requires its own approval.
   For allocation only, skip creation/issuance and select an existing issued credit
   and invoice explicitly. Read both, source lines, related credits/reconciliations
   and current balances in the original company. Missing status/balance/currency
   or incomplete duplicate reads means stop and ask.
5. The approved narrow ownership exception permits only allocation affecting that
   selected existing issued credit and invoice. Preview both identities, exact
   amount/date/currency/exchange-rate basis, provider-returned current balances,
   and provider-returned or explicitly user-supplied expected remaining balances
   with their source labels. Never derive expected balances or other accounting
   values; mark unavailable expectations as unavailable. Show duplicate evidence. Obtain separate approval for this exact allocation;
   draft approval is not allocation approval. If refused, stop without a write.
   Use `create_credit_note_reconciliation` once. FreeAgent decides eligibility,
   signs and over-allocation; inspect rejection rather than changing numbers to
   force acceptance. The helper reads reconciliation, credit note and invoice;
   compare provider-returned fields with the sourced preview, report provider-returned due/unapplied balances in
   each currency, and flag unexpected balances/relationships or partial failure.
   Allocation is not cash paid/refunded. Do not edit the invoice, issue the credit,
   change an old reconciliation or touch unrelated records under this exception.
6. For timeout, failed readback or partial outcome, STOP. Inspect original company,
   credit/invoice and complete reconciliation list. Reconcile what exists before
   asking whether to resume. Never blindly repeat a create, issuance transition or allocation. Re-read the credit
   status before considering another issuance; if already issued, do not replay.
   A retry after evidence establishes no transition requires fresh exact approval.

Hosted reads: `list_credit_notes`, `get_credit_note`, `list_credit_note_reconciliations`,
`get_credit_note_reconciliation`, `list_invoices`, `get_invoice`, `list_contacts`.
Use these remote tools directly in ChatGPT web or iOS. No client-local Python,
shell, filesystem, CLI or generic API executor is needed. Credit emailing, cash
refunds, cancellation and historical Draft issuance remain outside this workflow.
Live sandbox evidence remains a separate release gate.
