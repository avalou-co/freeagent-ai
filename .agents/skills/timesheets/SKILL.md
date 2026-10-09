---
name: timesheets
description: Log time to FreeAgent as timeslips for a date range (e.g. "log last week"). Use when the user asks to record, fill in or check timesheets.
argument-hint: "[date range]"
---

# Timesheets workflow

Generic. The business supplies the project, task and default hours; ask for them or find them in the business's own instructions. If the user gives names, resolve them with `GET projects?contact=...&view=active` and `GET tasks?project=...&view=active`. If a project or task does not exist, show the plan and, once approved, create it with `create_project` / `create_task` (see `docs/api-notes.md`).

1. Resolve dates from today's date. "Last week" means Mon to Sun before the current week. Confirm if ambiguous.
2. Working days are Mon to Fri minus days the user was out. Ask about bank holidays; do not assume.
3. `GET timeslips` for the range and skip dates that already have one. Report skips.
4. Show the plan (date, project, task, hours) and wait for approval, unless the user already gave the exact details and said to do it.
5. `POST timeslips` once per date.
6. `GET` the range again and report what FreeAgent holds.

If the user omits project or hours, use the business's defaults and say so in the report.

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
