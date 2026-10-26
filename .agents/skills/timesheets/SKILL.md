---
name: timesheets
description: Log time to FreeAgent as timeslips for a date range (e.g. "log last week"). Use when the user asks to record, fill in or check timesheets.
argument-hint: "[date range]"
---

# Timesheets workflow

The business supplies project, task and hours; ask for missing inputs. Use
`list_contacts`, `list_projects`, `list_tasks`, `list_users` and `get_current_user`
to resolve identities with declared filters; inspect `get_project` / `get_task`
when necessary. For approved new setup use `create_project` / `create_task`.
Use only named remote tools in ChatGPT web/iOS; no local runner is required.

1. Resolve the user's intended dates and hours. Confirm ambiguous date ranges and
   absences; never assume bank holidays or invent working hours.
2. Call `list_timeslips` for the user/date/project scope with paginate=true. Inspect
   details with `get_timeslip`; show existing records and resolve overlaps with the
   user. A failed lookup is not an empty history.
3. Show exact date, user, project, task, hours and comment for each proposed timeslip.
   Obtain approval of this plan; refusal or unresolved details mean no creation.
4. Call `create_timeslip` once for each approved entry. Compare its readback with
   the approved inputs, then use `get_timeslip` or `list_timeslips` if verification
   is incomplete. Report source records and provider values without invented totals.
5. On uncertain creation or failed readback, inspect the original account before
   any further creation. Never blindly replay a write or edit unrelated records.

Follow `docs/agent-rules.md` throughout.

For corrections, follow the shared [task correction rules](../../../docs/agent-rules.md#correcting-entries-created-in-the-current-task).
