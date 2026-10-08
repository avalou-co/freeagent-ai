---
name: reports
description: Read-only FreeAgent reports - profit and loss, balance sheet, trial balance, cash, and overdue invoices and bills. Use when the user asks how the business is doing, for a P&L, balance sheet, or what is overdue.
argument-hint: "[report] [from] [to]"
---

# Reports workflow

Read-only: use `freeagent_get` only, never write. The business supplies the date range and accounting period (e.g. financial year start); ask if missing. Endpoints: see `docs/api-notes.md`.

1. Profit and loss: `accounting/profit_and_loss/summary?from_date=&to_date=`.
2. Balance sheet: `accounting/balance_sheet?as_at_date=`.
3. Trial balance: `accounting/trial_balance/summary?from_date=&to_date=`.
4. Cash: `GET bank_accounts`, report each account's balance.
5. Overdue: `invoices?view=overdue` and `bills?view=overdue`. Follow `next` pages (`per_page=100&page=N`) and total the amounts per currency.
6. Report figures with their date range, state which endpoints returned them, and flag any call that failed or returned an unexpected shape instead of guessing.

Follow `docs/agent-rules.md` throughout.
