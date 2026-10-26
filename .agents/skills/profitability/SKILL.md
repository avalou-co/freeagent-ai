---
name: profitability
description: Read-only FreeAgent project, budget, task, time, invoice and cost-record evidence.
argument-hint: "[from date] [to date] [project or contact]"
---

# Project and billing records

Follow [agent rules](../../../docs/agent-rules.md) and
[provider evidence coverage](../../../docs/analysis.md). Read only.
The skill identifier is retained for compatibility; it does not calculate profitability.

1. Confirm company, period, selected contact/project and currency. Resolve identities
   with `list_contacts`, `list_projects` and `get_project`. Show provider project
   budget, budget_units, hours_per_day, status and source URL when returned.
   Do not calculate budget consumption or remaining budget from these fields.
2. Read `list_tasks` for the selected project (view=all), `list_timeslips`
   (view=all and requested date filters), `list_invoices`, `list_credit_notes`,
   `list_credit_note_reconciliations`, `list_expenses` and `list_bills` as needed.
   Use only declared filters; fetch details with the matching named get tool.
   Omit page and leave paginate=true. State which collections succeeded and when.
   Failed/denied reads or missing relationships remain unavailable coverage.
3. Present source records and their returned fields: task is_billable, timeslip
   hours, billed_on_invoice and timer; invoice/credit status, currency and signed
   net_value/total_value/due_value; expense/bill project and tax evidence. Link
   related records without computing revenue, costs, billable/unbilled hour totals,
   hourly revenue, margin, net profit, currency conversions or allocation amounts.
   An invoice link, including Draft, is evidence of linkage; running time is not
   final recorded time. Missing fields do not mean zero.
4. Explain the available evidence and unsupported questions. Use the reports skill
   for FreeAgent's own profit-and-loss, balance-sheet or trial-balance results.
   No project margin, internal cost-rate or profitability calculation endpoint is
   exposed; do not request internal rates to build a substitute accounting model.
5. For a selected invoicing follow-up, hand record identities to the invoicing
   workflow, re-read current sources and show the exact proposed provider action
   for approval. FreeAgent determines eligibility and duplicate-time billing.

Use named remote tools in ChatGPT web/iOS; no local Python, scripts, filesystem,
shell or assumed calculator. Do not reinterpret recorded payments as period cash
or describe incomplete project records as matched lifetime profit.
