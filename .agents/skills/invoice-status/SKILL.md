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

This workflow remains read-only. If the user explicitly requests an action, hand
off to the [invoicing workflow](../invoicing/SKILL.md) and
[approved invoice policy](../../../docs/invoicing.md#approved-invoice-delivery-and-duplication-policy).
That workflow requires current-request ownership for delivery/status, complete
review and distinct exact approval. Chaser-text approval alone never permits a
send; existing invoices cannot be sent under that ownership policy.
