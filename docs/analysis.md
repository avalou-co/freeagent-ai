# Read-only financial analysis

Issues #41 and #42 extend reports using the `cash-flow` and `profitability` skills.
The pure Python helpers in `freeagent_ai.analysis` take reviewed snapshots; they do
not fetch credentials, store accounting data, introduce MCP tools or write to FreeAgent.
Use existing paginated GET tools to collect data in local and hosted sessions.
The agent executes the arithmetic locally, retaining Decimal values until formatting
(`format(value, 'f')`); round only presentation with an agreed currency precision.

## Snapshot contract

Supply complete collections, a UTC retrieval timestamp, explicit scope and decimal
strings. Missing required fields fail; never replace missing money/hours with zero.
Duplicate source URLs fail instead of inflating totals. Preserve source URLs when
normalising evidence; use unique reviewed allocation/occurrence IDs for split costs
and commitments and retain parent source links in the review. Never save real
snapshots in this public repository. Permission errors are missing coverage, not
empty collections. Existing client pagination tests cover retrieval; calculation
fixtures are synthetic and require no account access.

Provider fields verified against official documentation on 2026-10-20:
[bank balances](https://dev.freeagent.com/docs/bank_accounts),
[invoice residual/net/settled values](https://dev.freeagent.com/docs/invoices),
[bill residuals](https://dev.freeagent.com/docs/bills),
[project budget units](https://dev.freeagent.com/docs/projects),
[task billability](https://dev.freeagent.com/docs/tasks),
[timeslip invoice links](https://dev.freeagent.com/docs/timeslips), and
[expenses](https://dev.freeagent.com/docs/expenses), and
[credit notes](https://dev.freeagent.com/docs/credit_notes).

## Forecast calculation

`forecast(start=date(...), timestamp=..., currency=..., accounts=[...],
invoices=[...], bills=[...], commitments=[...], receipt_delay_days=0,
missing_inputs=[...])` returns thirteen half-open seven-day buckets starting on the
selected date, not calendar weeks. Each closing = opening + receipts - payments;
the next opening equals the previous closing. Signed balances include overdrafts.
Only outstanding Open/Overdue/Part written-off residuals are projected; excluded
statuses are listed. Credits/refunds need reviewed signed commitments. Overdue
residuals land at start; the receipt delay applies after that floor. Bill dates do
not move under a receipt-delay scenario. Events beyond day 90 are reported separately.
The first shortfall is a negative weekly opening or closing, not an intraday promise.
All inputs in a run must use the selected currency; no implicit conversions.
Account assignment, unreconciled bank movements, transfers and commitment overlap
must be resolved by the agent/user before calling the helper. The helper cannot
prove an additional commitment is absent from a bank balance.

## Project calculation

`profitability(start=..., end=..., timestamp=..., projects=[...], tasks=[...],
timeslips=[...], invoices=[...], credit_notes=[...], costs=[...], cost_rates={user_url: '25.00'},
costs_complete=False)` uses inclusive dates. It returns project/contact evidence,
recorded/billable/unbilled hours, issued invoice net revenue less signed issued credit notes, costs and period budget
usage. Realised hourly revenue = issued net revenue / all recorded period hours;
zero hours returns unknown. This ratio mixes invoice dates and work dates and is
not a matched-work realisation measure. It works for hourly and fixed-fee work
without inventing earned revenue. No timeslip value is added to invoice revenue.

Time cost includes non-billable work. Missing user rates make time cost and margin
unknown. Direct cost is the known allocated subtotal; `costs_complete=False` makes
margin unknown even when that subtotal is zero. Unattributed costs are returned
for review, never assigned automatically. Cash receipts are not inferred from
invoice settlement values. Budget usage is hours, hours / project hours_per_day,
or issued net revenue for Monetary budgets. It describes only the input period;
remaining lifetime budgets need a separate complete-history calculation. Missing
or zero budgets must not be described as exhausted budgets.

Forecast start must equal the UTC snapshot date because the API supplies current
balances. For historical or future starts obtain reconciled balances and a reviewed
bridge separately; this helper does not model that bridge. Review write-offs and invoice adjustments before claiming margin; leave
costs_complete false when any revenue adjustments remain unresolved. Issued credit
notes enter credit_notes with the provider's signed negative net_value; allocation
to invoices does not make another revenue adjustment. Outstanding credit refunds
need reviewed signed cash commitments; allocations are not cash receipts.
