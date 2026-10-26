---
name: bills
description: Record a supplier bill in FreeAgent, or list unpaid and overdue bills. Use when the user asks to add, log or enter a supplier bill or purchase invoice, or asks what bills are due.
argument-hint: "[supplier]"
---

# Bills workflow

For uploaded receipt images or PDFs, first follow the [receipts workflow](../receipts/SKILL.md) (`/freeagent-ai:receipts`) for extraction, uncertainty and duplicate review. Return here to create only the reviewed, approved items.

Generic. The business supplies the supplier, categories, VAT treatment and how bills are attached. Ask for them or find them in the business's own instructions.

Listing: call `list_bills` with view=open (unpaid) or view=overdue; use `get_bill` for details.

Recording:

1. Find the supplier with `list_contacts` / `get_contact` and category with `list_categories` / `get_category`. Ask if unclear.
2. Call `list_bills` across all pages for the relevant dates and compare references to avoid duplicates.
3. Show the plan (reference, dates, lines, VAT, attachment) and get a clear yes.
4. Call `create_bill`. Pass the ChatGPT file reference in `attachment` for the supplier's PDF or image if the user has one, and pass the reviewed `currency`.
5. Report what FreeAgent holds: reference, dates, lines, totals, VAT, attachment. Flag any mismatch with the supplier's bill.

Never modify bills you did not create in this task. Follow `docs/agent-rules.md` throughout.

For corrections, follow the shared [task correction rules](../../../docs/agent-rules.md#correcting-entries-created-in-the-current-task).
