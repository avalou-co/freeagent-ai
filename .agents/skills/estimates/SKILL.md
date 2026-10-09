---
name: estimates
description: Create a draft FreeAgent estimate (quote) for a contact or project with line items. Use when the user asks to draft or prepare an estimate or quote.
argument-hint: "[contact or project]"
---

# Estimates workflow

Generic. The business supplies the contact, project, line items (description, unit, quantity, price), currency and reference format. Ask for them or find them in the business's own instructions.

1. Read the contact's latest estimate (`GET estimates?contact=...`) to copy reference style and currency.
2. Show the plan, get a clear yes, then call `create_draft_estimate`. It is always Draft and never sent.
3. Verify the returned status, line count and totals (net = quantity x price).
4. Report reference, lines and totals. Say the reference is an assumption if you inferred it.

Follow `docs/agent-rules.md` throughout.

For corrections, follow the shared [task correction rules](../../../docs/agent-rules.md#correcting-entries-created-in-the-current-task).
