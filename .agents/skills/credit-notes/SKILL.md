---
name: credit-notes
description: Review customer credits, create draft credit notes and prepare separately approved invoice allocations under the reviewed ownership policy.
---

# Credit notes

Follow [agent rules](../../../docs/agent-rules.md) and [credit policy](../../../docs/credit-notes.md).
Ask for the company, contact, invoice, reason, date, reference, terms, currency and
exact signed line quantities/prices/tax. Never assume a full refund, tax rate or exchange rate.

1. Resolve contact and invoice with reads. List all related credits including Draft,
   and all reconciliations (filter the complete collection by returned URLs). Read
   candidate details and source invoice lines. An incomplete/denied read blocks a
   duplicate conclusion and creation. A similar draft may already fulfil the request;
   show evidence and ask the user to resolve it rather than create another.
2. Preview contact/project, original invoice, exact signed lines, tax, currency,
   net/tax/gross totals, reference/terms and potential duplicates. Distinguish invoice
   credit allocation from cash refund. No status or sending action is implied.
3. Obtain approval of this exact draft. If refused, stop without any write. Use
   `create_draft_credit_note` once, then verify provider Draft status, reference,
   contact, currency, every line and totals. Never treat a POST response as readback.
   Report any changed or absent provider values and leave the credit unissued.
4. Issuing, marking sent, emailing and cash refunds remain outside this workflow.
   A new Draft stays unissued: do not transition it to enable allocation. If the
   request is allocation only, skip draft creation and select an existing issued
   credit and invoice explicitly. Read both records, source lines, all related
   credits/reconciliations and current balances in the original linked company.
   Missing status/balance/currency or incomplete duplicate reads means stop and ask.
5. The approved narrow ownership exception permits only allocation affecting that
   selected existing issued credit and invoice. Preview both identities, exact
   amount/date/currency/exchange-rate basis, current and expected remaining balances
   and duplicate evidence. Obtain separate approval for this exact allocation;
   draft approval is not allocation approval. If refused, stop without a write.
   Use `create_credit_note_reconciliation` once. FreeAgent decides eligibility,
   signs and over-allocation; inspect rejection rather than changing numbers to
   force acceptance. The helper reads reconciliation, credit note and invoice;
   compare all three with the preview, report actual due/unapplied balances in
   each currency, and flag unexpected balances/relationships or partial failure.
   Allocation is not cash paid/refunded. Do not edit the invoice, issue the credit,
   change an old reconciliation or touch unrelated records under this exception.
6. For timeout, failed readback or partial outcome, STOP. Inspect original company,
   credit/invoice and complete reconciliation list. Reconcile what exists before
   asking whether to resume. Never blindly repeat a create or reapply an allocation.

Hosted reads: `list_credit_notes`, `get_credit_note`, `list_credit_note_reconciliations`,
`get_credit_note_reconciliation`, `list_invoices`, `get_invoice`, `list_contacts`.
Use these remote tools directly in ChatGPT web or iOS. No client-local Python,
shell, filesystem, CLI or generic API executor is needed. Issuing/sending is not
provided by this workflow. Live sandbox evidence remains a separate release gate.
