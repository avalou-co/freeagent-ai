---
name: expenses
description: Record expense claims in FreeAgent with receipts (e.g. "log these receipts"). Use when the user asks to add or check expenses.
argument-hint: "[receipts or date range]"
---

# Expenses workflow

Generic. The business supplies the category and VAT rules; ask for them or find them in the business's own instructions.

1. Read each receipt for date, amount, VAT and a short description. Ask if any is unreadable; do not guess.
2. `GET users/me` for the user and `GET categories` to pick the category. Ask if unclear.
3. `GET expenses` for the dates and skip any that already exist. Report skips.
4. Show the plan (date, category, gross, VAT, description, receipt file) and wait for approval, unless the user already gave the exact details and said to do it.
5. `create_expense` once per receipt, passing `receipt_path` for the file.
6. Report what FreeAgent holds, including whether each attachment is present.

Mileage claims are not covered yet.

Follow `docs/agent-rules.md` throughout.

For corrections, follow the shared [task correction rules](../../../docs/agent-rules.md#correcting-entries-created-in-the-current-task).
