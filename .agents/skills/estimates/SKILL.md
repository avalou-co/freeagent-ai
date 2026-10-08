---
name: estimates
description: Create a draft FreeAgent estimate (quote) for a contact or project with line items. Use when the user asks to draft or prepare an estimate or quote.
argument-hint: "[contact or project]"
---

# Estimates

Follow `docs/agent-rules.md`. The business's own instructions give the contact, project, line items, currency and reference format.

1. Read the contact's latest estimate (`estimates?contact=...`) to copy its reference style and currency.
2. Show the plan and wait for a yes, then call `create_draft_estimate`. It always creates a Draft and never sends it.
3. Check the status, line count and totals (net = quantity × price).
4. Report the reference, lines and totals. Say so if you guessed the reference.
