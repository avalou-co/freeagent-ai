---
name: invoicing
description: Create a draft FreeAgent invoice for a project, optionally from its unbilled timeslips. Use when the user asks to raise, draft or prepare an invoice.
argument-hint: "[project]"
---

# Invoicing workflow

Generic. The business supplies the contact, project, bank account, reference format, payment terms, whether timeslips go on the invoice, and how invoices are delivered. Those are business decisions; ask for them or find them in the business's own instructions.

0. If the client is new, `find_contacts` first, then `create_contact` (after the user confirms the details) and use its URL as the contact.
1. Read the latest invoice for the project to copy reference style, terms, bank account and settings.
2. `POST invoices`. If the business bills from timeslips, set `include_timeslips` (e.g. `"billed_grouped_by_timeslip"`); FreeAgent bills each timeslip only once, so no double-billing check is needed. Add no placeholder items (see `docs/api-notes.md`).
3. `GET` the invoice and verify its status, line count and totals.
4. Report reference, due date, lines and totals. Say the reference number is an assumption if you inferred it.

Follow `docs/agent-rules.md` throughout.

## Correcting a mistake in this task

For MCP work, call `begin_task` once at the start and pass its `task_id` to create
calls. For a correction, show the exact changes or deletion and get a clear yes,
then use `update_created_entry` or `delete_created_entry` with that handle and
`confirmed=True`. Only entries created with this handle and still eligible can be
corrected; report external changes or protected status instead. Never reset status
or unlink billed work to bypass a refusal. Verify the returned readback (deletes
require verified absence). If a write or readback fails, inspect without retrying.
Call `finish_task` when done; never reuse the handle in another task.
See `docs/mcp.md` for supported fields, status gates and expiry.
