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
4. Before issuing OR allocating, STOP at the explicit policy gate in the linked
   policy document. Draft approval does not approve issuing, sending or allocation.
   Current instructions do not authorize allocations affecting pre-existing invoices.
   Do not use generic API tools to bypass this gate. Prepare a separate exact action
   preview; a general request to credit an invoice is not an ownership-policy change.
5. Only after the policy gate is explicitly reviewed and approved, and the exact
   allocation separately approved, use `create_credit_note_reconciliation` for the
   selected credit/invoice/amount/date/currency/exchange rate. Current-request
   ownership still applies unless explicitly changed by that reviewed decision.
   FreeAgent decides eligibility, signs and over-allocation. Inspect its rejection;
   do not change numbers to force acceptance. The helper reads reconciliation,
   credit note and invoice; report due/unapplied values in their own currencies,
   and distinguish allocation from cash paid/refunded. Missing balances are unknown.
6. For timeout, failed readback or partial outcome, STOP. Inspect original company,
   credit/invoice and complete reconciliation list. Reconcile what exists before
   asking whether to resume. Never blindly repeat a create or reapply an allocation.

Hosted reads: `list_credit_notes`, `get_credit_note`, `list_credit_note_reconciliations`,
`get_credit_note_reconciliation`, `list_invoices`, `get_invoice`, `list_contacts`.
Local reads use freeagent_get with the documented resources. Issuing/sending is not
provided by this workflow. Live sandbox evidence remains a separate release gate.
