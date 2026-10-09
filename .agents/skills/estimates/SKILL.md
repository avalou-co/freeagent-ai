---
name: estimates
description: Create a draft FreeAgent estimate (quote) for a contact or project with line items. Use when the user asks to draft or prepare an estimate or quote.
argument-hint: "[contact or project]"
---

# Estimates workflow

Generic. The business supplies the contact, project, line items (description, unit, quantity, price), currency and reference format. Ask for them or find them in the business's own instructions.

1. Read the contact's latest estimate (`GET estimates?contact=...`) to copy reference style and currency.
2. Show the plan, get a clear yes, then call `create_draft_estimate`. It is always Draft and never sent.
3. Verify the returned status, line count and totals (net = quantity x price).
4. Report reference, lines and totals. Say the reference is an assumption if you inferred it.

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
