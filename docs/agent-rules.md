# Agent rules

- Use the API, not a browser.
- Never print, log, commit or paste secrets or tokens.
- Reads are free. Writes (timeslips, invoices, expenses, bills, bank explanations) need the plan shown and a clear yes, unless the user already gave exact details and told you to proceed.
- After every write, read it back and report what FreeAgent holds.
- Do not modify or delete entries you did not create in this task; report conflicts instead.

## Correcting entries created in the current task

Only modify or delete entries you created during the current user request. Show
exact changes or deletion and obtain a clear yes. Use `freeagent_put` or
`freeagent_delete` with `confirmed=True`, then read back with `freeagent_get`.
Use the resource or its parent to verify the outcome; an empty successful response
is not a readback. Report conflicting edits rather than changing unrelated entries.
For any uncertain write or failed readback, inspect before retrying or recreating.

Ownership and approval are agent responsibilities. FreeAgent handles accounting,
model and relationship validation. The MCP tools pass API payloads through
unchanged and do not duplicate those rules.
See [API write tools](mcp.md#correcting-entries-created-in-a-task).
