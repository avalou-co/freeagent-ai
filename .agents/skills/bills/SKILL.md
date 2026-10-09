---
name: bills
description: Record a supplier bill in FreeAgent, or list unpaid and overdue bills. Use when the user asks to add, log or enter a supplier bill or purchase invoice, or asks what bills are due.
argument-hint: "[supplier]"
---

# Bills workflow

Generic. The business supplies the supplier, categories, VAT treatment and how bills are attached. Ask for them or find them in the business's own instructions.

Listing: `freeagent_get` `bills?view=open` (unpaid) or `bills?view=overdue`.

Recording:

1. Find the supplier contact (`contacts`) and the category for each line (`categories`). Ask if unclear.
2. Check `bills?from_date=&to_date=` for the same reference to avoid duplicates.
3. Show the plan (reference, dates, lines, VAT, attachment) and get a clear yes.
4. Call `create_bill`. Pass `attachment_path` for the supplier's PDF or image if the user has one.
5. Report what FreeAgent holds: reference, dates, lines, totals, VAT, attachment. Flag any mismatch with the supplier's bill.

Never modify bills you did not create in this task. Follow `docs/agent-rules.md` throughout.

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
