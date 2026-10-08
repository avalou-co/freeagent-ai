---
name: bills
description: Record a supplier bill in FreeAgent, or list unpaid and overdue bills. Use when the user asks to add, log or enter a supplier bill or purchase invoice, or asks what bills are due.
argument-hint: "[supplier]"
---

# Bills

Follow `docs/agent-rules.md`. The business's own instructions give the supplier, categories and VAT treatment.

`Listing.` Call `freeagent_get` with `bills?view=open` for unpaid bills or `bills?view=overdue`.

`Recording.`

1. Find the supplier in `contacts` and a category for each line in `categories`.
2. Check `bills?from_date=&to_date=` for a bill with the same reference.
3. Show the reference, dates, lines, VAT and attachment, and wait for a yes.
4. Call `create_bill`. Pass `attachment_path` if the user has the supplier's PDF or image.
5. Report the reference, dates, lines, totals, VAT and attachment, and flag anything that differs from the supplier's bill.
