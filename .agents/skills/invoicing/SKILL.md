---
name: invoicing
description: Prepare draft FreeAgent invoices, duplicate reviewed sources and separately approve sending or marking a current-request invoice sent, using remote provider tools.
argument-hint: "[client or project]"
---

# Invoicing workflow

Use the named remote tools below from marketplace-installed ChatGPT on web/iOS.
No local Python, shell, filesystem or generic API executor is required. Follow
[agent rules](../../../docs/agent-rules.md) and [invoice contract](../../../docs/invoicing.md).

1. Establish company, client, optional project, invoice date, currency, payment
   terms, bank account and reference from the user's instructions. Call
   `get_company`, `list_contacts` and `get_contact`; match the returned names and
   resolve ambiguity with the user. If a new contact is needed, preview its exact
   details, obtain approval and call `create_contact`. Do not infer business defaults.
2. Call `list_projects`, `get_project`, `list_invoices` and `get_invoice` as needed
   to inspect provider evidence and prior settings. Read every page; a failed or
   incomplete read is not an empty collection. Use numeric IDs for top-level tool
   parameters, but full returned provider URLs inside nested invoice payloads.
3. Ask whether to use manual `invoice_items` or include eligible project sources.
   Read selected records using `list_estimates`/`get_estimate`,
   `list_expenses`/`get_expense`, `list_bills`/`get_bill` and
   `list_timeslips`/`get_timeslip`. Inspect source lines, status, project, currency,
   tax and rebilling/invoice relationships. Estimate status Approved is provider
   state, not user approval to create an invoice. Do not change source records.
4. Provider `include_estimates` modes include open/approved estimates;
   `include_expenses` modes include expenses, bills **and bank account entries**.
   These are grouping modes, not a list of individually selected source IDs. Review
   the whole eligible project scope, including `list_bank_transactions` and
   `get_bank_transaction_explanation` where relevant. If exact inclusion cannot be
   established from complete provider evidence, stop and explain the limitation;
   ask the user to narrow/resolve the scope rather than claim exact selection.
   FreeAgent decides eligibility and prevents duplicate billing; no local eligibility,
   invoice-total, tax or exchange-rate calculations are performed.
5. Preview the exact proposed payload: contact/project, date, terms, currency,
   reference/bank account, each manual line's description, quantity, price, tax and
   category, and every inclusion mode with its reviewed source evidence. Label
   provider-returned totals and user-supplied expectations by source. If there is no
   provider quote endpoint, a pre-write invoice total is unavailable: do not compute
   one. Status is fixed to Draft and all three automatic email flags are off. Never add
   placeholder manual lines alongside included sources. Obtain separate, explicit
   approval for this exact creation; source approval does not authorize the write.
6. Call `create_draft_invoice_from_payload` with the reviewed `invoice` object and
   `confirmed: true`. It forwards documented manual/source fields, forces Draft and
   automatic emails off, then reads back. `create_draft_invoice` remains the narrower
   timeslip convenience operation; do not use it as a workaround for missing fields.
7. Inspect the actual returned invoice with `get_invoice` if needed: Draft status,
   emails off, currency, provider totals, actual invoice-item identities/lines and
   available source relationships. Re-read the source records to verify their
   returned invoicing/rebilling state. Flag unexpected lines, missing relationships,
   amounts or statuses before further action. Do not derive missing links or totals.
   Report reference, due date, provider amounts and source links. Do not send or
   mark sent without the separate action workflow below; never mark paid. After any timeout, partial failure or failed readback,
   inspect the original company and created resource before another create; never replay blindly.

For corrections, follow the shared current-request ownership and approval rules.

## Separately approved invoice actions

Follow the [approved invoice policy](../../../docs/invoicing.md#approved-invoice-delivery-and-duplication-policy)
for any action beyond draft creation. Keep document review, duplicate review,
creation, accounting transition and actual email approvals distinct.

1. For a new copy, inspect the original company/source invoice and all duplicate
   candidates first. Preview the selected source and new-Draft intent, obtain
   exact approval, then call `duplicate_invoice` with numeric `id` and
   `confirmed: true`. Inspect the returned new invoice and `source_invoice`;
   verify actual date/reference, complete lines and automatic-email settings.
   The source remains read-only; creating the copy never authorizes sending it.
2. Status/email actions apply only to an invoice created and read back during this
   user request in the original company. Refuse actions on historical invoices,
   missing ownership or conflicting updates. Inspect current provider state and
   verify all three automatic-email settings off. For a current-request Draft,
   preview mark-as-sent and obtain separate explicit transition approval before
   calling `mark_invoice_as_sent`. It reads back accounting status, not delivery.
   Do not reopen, cancel, schedule, mark paid or collect payment.
3. Before email, review the selected document through the authenticated document
   workflow where available; otherwise ask the user to review this exact invoice
   in FreeAgent and confirm identity/content. Missing document review blocks send.
   Preview exact company/invoice, `to`, registered-user `from`, `subject`, complete
   `body`, explicit `email_to_sender`, no extra attachments/expense receipts and
   all automatic-email settings. Resolve wrong/missing recipients and any contact
   mismatch with the user. Do not invent addresses, sender, wording or defaults.
   Templates and extra attachments are unsupported: offer sending in FreeAgent.
4. Obtain approval to **send this exact email now**, distinct from draft, duplicate
   and transition approval or approval of chaser text. Then call `send_invoice_email`
   with numeric `id`, the reviewed `email` object and `confirmed: true`. Never call
   on refusal or uncertain approval. The helper fixes expense-receipt inclusion
   off, forwards explicit fields and reads back the invoice.
5. Report `request_accepted` as API acceptance and `recipient_delivery` as
   unavailable, alongside returned invoice state. Status is not receipt/delivery
   or payment proof. If document, recipients or settings changed, stop for renewed
   review/approval. On timeout, disconnect, provider rejection or failed readback,
   inspect the original company/record and available evidence before any next
   action. Do not replay email or duplication, or infer non-delivery from unchanged
   status. If provider evidence cannot resolve acceptance, ask the user to inspect
   FreeAgent; never blindly retry.
