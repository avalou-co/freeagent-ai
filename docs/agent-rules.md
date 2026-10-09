# Agent rules

- Use the API, not a browser.
- Never print, log, commit or paste secrets or tokens.
- Reads are free. Writes (timeslips, invoices, expenses, bills, bank explanations) need the plan shown and a clear yes, unless the user already gave exact details and told you to proceed.
- After every write, read it back and report what FreeAgent holds.
- Do not modify or delete entries you did not create in this task; report conflicts instead.

## Correcting entries created in the current task

For MCP work, call `begin_task` once at the start and pass its `task_id` to supported
create calls. To correct a mistake, show the exact changes or deletion and obtain
a clear yes, then use `update_created_entry` or `delete_created_entry` with that
handle and `confirmed=True`. Only entries created with this handle and still
eligible can be corrected; report external changes or protected status instead.
Never reset status or unlink billed work to bypass a refusal. Report the returned
readback; deletion requires verified absence. If a write or readback fails,
inspect without retrying. Call `finish_task` when done and never reuse the handle
in another task. See [MCP correction tools](mcp.md#correcting-entries-created-in-a-task)
for supported fields, status gates and expiry.
