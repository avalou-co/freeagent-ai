---
name: invoice-status
description: Read-only list of FreeAgent invoices by status, contact or date, with payment status, and draft text to chase overdue ones. Use for "what's outstanding?", "who owes me?" or "chase this invoice".
argument-hint: "[contact]"
---

# Invoice status workflow

Read-only: use named remote tools on ChatGPT web/iOS. Never send emails or
reminders, mark paid or mutate an invoice. No local runtime is required.

1. Resolve the selected contact with `list_contacts` / `get_contact`. Call
   `list_invoices` with declared view/contact/project filters and paginate=true;
   filter requested dates against returned records if no server date filter exists
   and disclose that limitation. Incomplete reads are unavailable coverage.
2. Fetch selected details with `get_invoice`. Report source URL, reference,
   contact, dated_on, due_on, status, total_value, due_value and currency exactly
   where returned. Do not derive balances, sum currencies or infer bank settlement.
3. Explain provider status and due dates. Do not invent missing payment/overdue
   data or use a custom accounting calculator.
4. To chase, draft text for the user to review and send themselves. Ask for the
   business's tone, wording and chase schedule when missing.

Follow `docs/agent-rules.md` throughout.

The [proposed delivery policy](../../../docs/invoicing.md#proposed-delivery-policy--pending-human-acceptance)
is pending human acceptance. Chaser drafting stays read-only; do not send, duplicate
or change status, even if an invoice is existing/issued or OAuth grants write scope. There
is no approved sending workflow to enter until that policy is accepted and the
named remote implementation is separately reviewed.
