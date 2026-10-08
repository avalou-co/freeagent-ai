---
name: timesheets
description: Log time to FreeAgent as timeslips for a date range (e.g. "log last week"). Use when the user asks to record, fill in or check timesheets.
argument-hint: "[date range]"
---

# Timesheets

Follow `docs/agent-rules.md`. The business's own instructions give the project, task and hours per day. If the user leaves any out, use those defaults and say so in the report.

1. Work out the dates from today. "Last week" means Monday to Sunday of the week before this one. Ask if the range is unclear.
2. Count Monday to Friday, less days the user was off. Ask about bank holidays.
3. Find the project and task with `projects?contact=...&view=active` and `tasks?project=...&view=active`. If one does not exist, include it in the plan and create it with `create_project` or `create_task`.
4. Check `timeslips` for the range and skip dates that already have one. Report the skips.
5. Show the date, project, task and hours for each day, and wait for a yes.
6. Call `create_timeslip` once per date.
7. Read the range back and report what FreeAgent holds.
