---
name: invoice-status
description: Read-only list of FreeAgent invoices by status, contact or date, with payment status, and draft text to chase overdue ones. Use for "what's outstanding?", "who owes me?" or "chase this invoice".
argument-hint: "[contact]"
---

# Invoice status workflow

Read-only: use `freeagent_get` only. Never send emails or reminders, mark invoices paid, or change an invoice.

1. List with `GET invoices?view=open_or_overdue&per_page=100`. Narrow with `contact=<url>` and `from_date`/`to_date`; other views include `overdue`, `open`, `draft`, `paid`. If a filter is ignored, filter the response yourself and say so. `freeagent_get` aggregates linked pages automatically; use it once for the list. If manually paging, set `paginate=False` on every call to avoid counting invoices twice.
2. For each invoice report reference, contact, `dated_on`, `due_on`, `status`, `total_value`, `due_value` and currency. Resolve contact names with `GET` on the contact URL. Don't sum across currencies.
3. Compute days overdue from `due_on` and today's date.
4. To chase, draft text for the user to review and send themselves. Tone, wording and chase schedule come from the business's own instructions; ask if missing.

Follow `docs/agent-rules.md` throughout.
