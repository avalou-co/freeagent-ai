# Agent rules

- Use the API, not a browser.
- Never print, log, commit or paste secrets or tokens.
- Reads are free. Writes (timeslips, invoices, expenses, bills, bank explanations) need the plan shown and a clear yes, unless the user already gave exact details and told you to proceed.
- After every write, read it back and report what FreeAgent holds.
- Do not modify or delete entries you did not create in this task; report conflicts instead. The only allocation exception is defined below.

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

## Approved credit-allocation exception

A narrow exception permits a credit-note reconciliation affecting a specifically
selected existing issued credit note and existing invoice. Read both records and
all related credits/reconciliations completely first. Show the original company,
both record identities, exact allocation amount/date/currency/exchange-rate basis,
provider-returned current balances and provider-returned or explicitly user-supplied
expected resulting balances, labelled by source. Never calculate balances, totals,
tax or exchange conversions; unavailable provider expectations stay unavailable.
Resolve duplicates or unavailable prerequisite evidence before writing. Obtain
separate approval for this exact allocation, even
when draft creation was approved. Submit once, then read the reconciliation, credit
note and invoice and report provider-returned remaining/unapplied balances and any
partial failure. Inspect uncertain outcomes before retrying; never blindly replay a write.

This exception authorizes only the selected credit/invoice allocation's balance
effect. It does not authorize invoice edits, credit-note issuing/status changes,
email/sending, cash refunds, unrelated records or changes to old reconciliations.
Use only an existing issued credit with provider-supported allocation eligibility;
FreeAgent validates eligibility, signs and over-allocation. Issuance is never implied by allocation approval; a current-request Draft may
be issued only with its separate exact approval under the policy below. All other current-request ownership rules
remain active. See [credit workflow](credit-notes.md).

## Current-request credit issuance

Issue only a Draft created and successfully read back in this user request and
original company. Preview the exact document and provider financial evidence,
resolve duplicate/incomplete reads and obtain separate explicit issuance approval.
Use `issue_credit_note` once. Read credit status/lines/balances back, and re-read
source invoice and related reconciliations where applicable. Draft creation or
allocation approval never approves issuance. Older drafts, reopening cancelled
credits, email, refunds and unrelated edits remain excluded. On uncertain outcome
or failed readback, inspect the original credit/status before any retry; never
blindly replay or allocate as a workaround. See [credit policy](credit-notes.md).
