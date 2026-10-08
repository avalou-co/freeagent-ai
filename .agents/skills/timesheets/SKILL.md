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
