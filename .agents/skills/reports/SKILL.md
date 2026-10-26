---
name: reports
description: Read-only FreeAgent profit and loss, balance sheet, trial balance, bank balances and overdue records.
argument-hint: "[report] [from] [to]"
---

# FreeAgent reports

Follow [agent rules](../../../docs/agent-rules.md) and
[provider evidence coverage](../../../docs/analysis.md). Read only.
Ask for the company, date range and accounting period; never guess financial-year dates.

1. Profit and loss: call `get_profit_and_loss` with the requested from_date/to_date.
2. Balance sheet: call `get_balance_sheet` with as_at_date.
3. Trial balance: call `get_trial_balance` with the requested from_date/to_date.
4. Bank balances: call `list_bank_accounts` and show each provider current_balance,
   currency, latest_activity_date and source URL. These are current snapshots.
5. Overdue records: call `list_invoices` and `list_bills` with view=overdue.
   Omit page and retain paginate=true. Present returned due_value, dates, currency
   and source links; use provider summary totals only when actually returned.
6. Explain the provider's report values with their report dates and collection
   timestamp. Preserve signs, labels and currencies. A failed/denied endpoint or
   missing amount is unavailable evidence, not zero or a successful empty report.

Use cash-flow for bank/outstanding-record evidence and profitability for project
records. Those compatibility skill names do not provide custom forecasts or margin
calculations. Do not derive new accounting metrics, cash commitments or budget
calculations. These skills need only named remote tools on ChatGPT web/iOS, never
client Python, a terminal or a local file.
