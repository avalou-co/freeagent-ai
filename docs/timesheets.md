# Timesheets workflow

Generic. The consuming repo supplies the project, task and default hours.

1. Resolve dates from today's date. "Last week" means Mon to Sun before the current week. Confirm if ambiguous.
2. Working days are Mon to Fri minus days the user was out. Ask about bank holidays; do not assume.
3. `GET timeslips` for the range and skip dates that already have one. Report skips.
4. Show the plan (date, project, task, hours) and wait for approval, unless the user already gave the exact details and said to do it.
5. `POST timeslips` once per date.
6. `GET` the range again and report what FreeAgent holds.

If the user omits project or hours, use the consuming repo's defaults and say so in the report.
