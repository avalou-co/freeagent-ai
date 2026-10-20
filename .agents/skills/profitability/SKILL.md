---
name: profitability
description: Read-only project/contact revenue, time, budgets, costs and unbilled-work review.
argument-hint: "[from date] [to date] [project or contact]"
---

# Profitability review

Follow `docs/agent-rules.md` and `docs/analysis.md`. GET tools only for analysis.

1. Confirm inclusive period, projects/contacts and currency. Ask for internal hourly
   cost rates by user and currency before estimating time cost/margin. Missing costs
   remain unknown. Confirm completeness including costs outside FreeAgent.
2. Read `projects?view=all&per_page=100`, tasks for each project including inactive
   tasks, `timeslips?view=all&from_date=...&to_date=...&per_page=100`,
   `invoices?view=all&per_page=100`, `credit_notes?per_page=100`, period expenses and bills. Use automatic
   pagination once per collection. Stop on failed/incomplete reads; record UTC time.
3. Join time to task `is_billable`, project and `billed_on_invoice`. A draft invoice
   link also means time is not unbilled. Resolve running timers/missing tasks.
   Use issued invoice `net_value` by `dated_on`, excluding Draft/Scheduled To Email.
   Include issued credit notes as signed negative net revenue, retaining their URLs.
   Review write-offs/adjustments before claiming margin. Fixed-fee revenue comes from invoices; never also add estimated timeslip value.
4. Review expense/bill cost allocations; use net amounts consistently and resolve
   VAT, currency and rebilling. Normalise expense negatives to positive costs and
   refunds to negative costs. Split mixed-project bills with distinct allocation IDs
   and parent links; never also count the header. Keep unattributed costs visible.
5. Run `freeagent_ai.analysis.profitability` with reviewed snapshots. Cost rows have
   `url`, optional `project`, `dated_on`, `currency`, signed decimal `amount`;
   Pass collected credit_notes separately.
   cost_rates maps user URLs to confirmed decimal hourly rates in project currency.
   Set costs_complete only when confirmed. Run separately per currency.
6. Show project rows grouped by contact: recorded, billable, non-billable (recorded
   minus billable) and unbilled hours, issued net revenue, realised revenue per all
   recorded period hours, costs/missing rates and budget consumption. Contact totals
   sum amounts/hours by currency; recompute ratios from totals, never average ratios.
   Unknown costs propagate to contact totals. Do not call period activity matched
   lifetime profit. Cash is separate: cumulative paid_value is neither period cash
   receipts nor necessarily bank cash. Show unavailable costs and unattributed rows.
7. Budget usage is for the input period only. For lifetime remaining budget fetch
   complete history through end date, rerun and subtract usage from budget. Hours
   and Days use recorded hours (Days requires hours_per_day); Monetary uses issued
   net revenue, excluding unbilled WIP. State this limitation; zero means no budget.
8. Offer reviewed handoff of selected unbilled_sources to the existing invoicing
   skill. Show exact selection, obtain approval and re-read time/invoices before any
   draft. Provider duplicate-time protection remains authoritative. Project-wide
   include_timeslips may include time outside the period: preview actual inclusion.
