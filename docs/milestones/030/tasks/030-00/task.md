# 030-00: Correct entries created by the agent in the current task

Tracks GitHub issue [#30](https://github.com/avalou-co/freeagent-ai/issues/30).

## Scope

Add MCP update/delete tools for entries created with an opaque task handle.
Support timeslips, draft invoices/estimates, unrebilled expenses, and wholly
unpaid/unrebilled bills. Refuse unowned entries, protected statuses, unsupported
fields, cross-entry line IDs, external changes, and unconfirmed writes.
Read back updates and verify absence after deletion. Revoke correction rights
on ambiguous writes and failed readbacks. Document workflow and lifecycle limits.

## Acceptance criteria

- Ownership comes only from successful create/readback in the task; no adoption.
- Status checks and user-confirmation assertion precede every correction write.
- Invoice updates disable email flags and cannot change status or relationships.
- Correct line IDs belong to the parent entry; foreign line IDs are rejected.
- Task close, replacement, expiry and restart discard correction rights.
- Meaningful mocked tests and in-memory MCP transport tests cover refusals and success.
- Ruff lint/format, Pyright and pytest pass. No live financial writes in verification.

## Verification

See the implementation PR for local and CI results. The transport tests use the
installed MCP SDK; API operations use dummy data and mocks. This change does not
claim live sandbox verification or atomic protection against external edits
between a FreeAgent read and write.
