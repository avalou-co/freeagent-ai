---
name: expenses
description: Record expense claims in FreeAgent with receipts (e.g. "log these receipts"). Use when the user asks to add or check expenses.
argument-hint: "[receipts or date range]"
---

# Expenses workflow

Generic. The business supplies the category and VAT rules; ask for them or find them in the business's own instructions.

1. Read each receipt for date, amount, VAT and a short description. Ask if any is unreadable; do not guess.
2. `GET users/me` for the user and `GET categories` to pick the category. Ask if unclear.
3. `GET expenses` for the dates and skip any that already exist. Report skips.
4. Show the plan (date, category, gross, VAT, description, receipt file) and wait for approval, unless the user already gave the exact details and said to do it.
5. `create_expense` once per receipt, passing `receipt_path` for the file.
6. Report what FreeAgent holds, including whether each attachment is present.

Mileage claims are not covered yet.

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
