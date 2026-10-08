---
name: invoicing
description: Create a draft FreeAgent invoice for a project, optionally from its unbilled timeslips. Use when the user asks to raise, draft or prepare an invoice.
argument-hint: "[project]"
---

# Invoicing

Follow `docs/agent-rules.md`. The business's own instructions give the contact, project, bank account, reference format, payment terms, whether to bill from timeslips and how invoices reach the client.

1. For a new client, search with `find_contacts`. If there is no match, confirm the details and call `create_contact`.
2. Read the project's latest invoice to copy its reference style, terms, bank account and settings.
3. Call `create_draft_invoice`. To bill from timeslips, set `include_timeslips` to `"billed_grouped_by_timeslip"` and add no other items (see `docs/api-notes.md`).
4. Check the status, line count and totals.
5. Report the reference, due date, lines and totals. Say so if you guessed the reference.
