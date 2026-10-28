---
name: estimates
description: Create a draft FreeAgent estimate (quote) for a contact or project with line items. Use when the user asks to draft or prepare an estimate or quote.
argument-hint: "[contact or project]"
---

# Estimates workflow

Generic. The business supplies the contact, project, line items (description, unit, quantity, price), currency and reference format. Ask for them or find them in the business's own instructions.

1. Resolve the selected contact/project using `list_contacts`, `list_projects` and their detail tools. Call `list_estimates` with declared filters and `get_estimate` for selected source records; ask the user to approve reference, currency and supplied line values.
2. Include the document type in the plan: `Estimate`, `Quote` or `Proposal`, matching the user’s request; clarify if unclear. Get a clear yes, then call `create_draft_estimate` with that `estimate_type`. It is always Draft and never sent.
3. Compare provider-returned document type, status, lines, totals and currency to the approved inputs. Never calculate taxes or totals locally.
4. Report reference, lines and totals. Say the reference is an assumption if you inferred it.

Follow `docs/agent-rules.md` throughout.

For corrections, follow the shared [task correction rules](../../../docs/agent-rules.md#correcting-entries-created-in-the-current-task).
