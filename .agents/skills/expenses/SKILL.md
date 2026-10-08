---
name: expenses
description: Record expense claims in FreeAgent with receipts (e.g. "log these receipts"). Use when the user asks to add or check expenses.
argument-hint: "[receipts or date range]"
---

# Expenses

Follow `docs/agent-rules.md`. The business's own instructions give the categories and VAT rules.

1. Read the date, amount, VAT and a short description off each receipt. Ask about any you cannot read.
2. Get the user from `users/me` and pick a category from `categories`.
3. Check `expenses` for those dates and skip any already recorded. Report the skips.
4. Show the date, category, gross, VAT, description and receipt file for each, and wait for a yes.
5. Call `create_expense` once per receipt, with `receipt_path` set to the file.
6. Report what FreeAgent holds, including whether each receipt attached.

Mileage claims are not supported yet.
