# Agent rules

- Use the API, not a browser.
- Never print, log, commit or paste secrets or tokens.
- Reads are free. Writes (timeslips, invoices, expenses, bills, bank explanations) need the plan shown and a clear yes, unless the user already gave exact details and told you to proceed.
- After every write, read it back and report what FreeAgent holds.
- Do not modify or delete entries you did not create in this task; report conflicts instead.

## Correcting entries created in the current task

Only correct entries you created during the current user request. Show the exact
changes or deletion and obtain a clear yes, then use `update_created_entry` or
`delete_created_entry` with `confirmed=True`. Ownership and approval are agent
responsibilities; the server checks current status and supported fields, but does
not track which conversation created an entry. Report conflicts instead of
changing unrelated entries. Never reset status or unlink billed work to bypass a
refusal. Report the readback; deletion requires verified absence. If a write or
readback fails, inspect without retrying or recreating the entry.
See [MCP correction tools](mcp.md#correcting-entries-created-in-a-task) for fields
and status gates.
