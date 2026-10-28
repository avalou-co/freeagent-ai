---
name: invoicing
description: Prepare approved draft FreeAgent invoices with manual lines or documented source inclusion, using remote provider tools.
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
   Report reference, due date, provider amounts and source links. Do not send, mark
   paid or issue the invoice. After any timeout, partial failure or failed readback,
   inspect the original company and created resource before another create; never replay blindly.

For corrections, follow the shared current-request ownership and approval rules.

Delivery, duplication and status changes remain unavailable. The
[proposed delivery policy](../../../docs/invoicing.md#proposed-delivery-policy--pending-human-acceptance)
is pending human acceptance and separate implementation; do not execute its
proposed steps, use generic API writes as a workaround, or treat draft approval
as permission to send. Offer reviewed draft text and direct the user to FreeAgent
for actions outside the current policy.
