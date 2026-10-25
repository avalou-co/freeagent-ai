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

## Hosted field coverage

Checked against the linked provider attribute and response contracts on 2026-10-25.
The same fields survive list and detail projections. For credit-note lines, request
`nested_credit_note_items="true"` or fetch the individual credit note. Reads aggregate linked pages
by default. For complete snapshots omit `page` and leave `paginate` true. Hosted
resource filters take numeric IDs; the dispatcher expands these to account-bound
provider URLs. Local `freeagent_get` remains available without projection changes.

| Analysis input | Hosted operation | Preserved fields and review |
| --- | --- | --- |
| Selected cash accounts | `list_bank_accounts`, `get_bank_account` | `url`, `currency`, `current_balance`, `latest_activity_date`, `is_personal`, `status`; missing activity date remains unknown, not a claim of freshness |
| Outstanding receivables | `list_invoices`, `get_invoice` | `url`, `project`, `contact`, `dated_on`, `due_on`, `status`, `currency`, `net_value`, `total_value`, `due_value`, `paid_value`; use residuals, not totals or settlement as period cash |
| Outstanding payables | `list_bills`, `get_bill` | `url`, `dated_on`, `due_on`, `status`, `currency`, `due_value`, `net_value`, `total_value`, `sales_tax_value`; retain `project`, `rebill_to_project`, `rebill_type`, `rebill_factor` and `bill_items` for reviewed cost allocation |
| Credit revenue/refunds | `list_credit_notes`, `get_credit_note` | `url`, `contact`, `project`, `reference`, `dated_on`, `due_on`, `status`, `currency`, signed `net_value`, `sales_tax_value`, `total_value`, `due_value`, `refunded_value`, `refunded_on`, `written_off_date`, `credit_note_items`; never take absolute revenue or infer a refund date |
| Credit allocation context | `list_credit_note_reconciliations`, `get_credit_note_reconciliation` | `url`, `credit_note`, `invoice`, `dated_on`, `currency`, `gross_value`, `exchange_rate`; a reconciliation is an allocation, not another cash payment or revenue adjustment |
| Project grouping/budget | `list_projects`, `get_project` | `url`, `contact`, `currency`, `budget`, `budget_units`, `hours_per_day`; day budgets need the provider's day length |
| Task billability | `list_tasks`, `get_task` | `url`, `project`, `is_billable`, `currency`, `billing_rate`, `billing_period`, `status`; fetch all tasks including inactive ones |
| Recorded/unbilled time | `list_timeslips`, `get_timeslip` | `url`, `project`, `task`, `user`, `dated_on`, `hours`, `billed_on_invoice`, `timer.running`, `timer.start_from`; `view=all` supported; a Draft invoice link still excludes time from unbilled WIP |
| Expense cost evidence | `list_expenses`, `get_expense` | `url`, `project`, `dated_on`, `currency`, `gross_value`, `sales_tax_value`, `native_gross_value`, `native_sales_tax_value`, `manual_sales_tax_amount` (company-native currency), second tax fields, tax status, `rebill_to_project`, `rebill_type`, `rebill_factor`, `rebilled_on_invoice`; review signed net costs, currency/tax basis and allocation |
| Bill item evidence | Bill reads above | `bill_items` preserve `url`, `bill`, `project`, `category`, `total_value`, `total_value_ex_tax`, tax amounts/rates/status; never count a whole bill and its allocated lines together |
| Sales line evidence | Invoice/credit-note reads above | line `url`, `project`, `invoice_item`, quantity/price and tax fields support source review; credit-note item links are evidence, not inferred allocation cash |
| Additional commitments/cost rates | User-reviewed input | No API projection can prove external commitments absent, establish account assignment or supply internal hourly rates. Confirm overlap and completeness explicitly |

Credit-note collection filters are `view`, `contact`, `project`, `updated_since`, `sort`, and
`nested_credit_note_items` (string `"true"`/`"false"`); reconciliation
filters are `from_date`, `to_date`, `updated_since`. Hosted contact/project filters
accept numeric IDs and expand them to provider references. Credit-note date-range
filters are not exposed; select the requested dates from the complete collection.
Keep native and transaction-currency tax amounts separate. Where the available
evidence cannot establish a consistent net-cost basis, leave costs incomplete and
ask for the missing allocation or tax detail rather than subtract unlike currencies.
The provider's reconciliation detail JSON example uses a plural root while its
XML/create examples use singular; hosted detail reads accept either spelling and
return the canonical singular root. Verify this shape in a dedicated sandbox before
claiming live provider compatibility.

`analysis.IncompleteData` explicitly rejects snapshots missing required calculation
fields or linked tasks. Hosted read errors return `isError=true` with “Read
incomplete”; do not turn permission errors, page failures or invalid projections
into empty lists. Stop collection and report which operation failed. A failed
required read cannot be repaired by passing `missing_inputs=[]`. Optional absent
`billed_on_invoice` and `timer` follow the documented provider convention (no linked
invoice/running timer); their projection is now retained when present. Resolve
running timers before calculating. Missing optional budgets mean unknown budget,
not zero. Normalise provider numeric zero budgets to decimal string `"0"` explicitly
before arithmetic; do not generalise this into defaulting missing amounts.

Forecast results carry `status="incomplete"` when reviewed `missing_inputs` remain.
Profitability results carry `status="incomplete"` when costs are not confirmed
complete or user rates are missing; known subtotals are still evidence, not complete
margin. Required missing fields raise instead of producing totals. Sign/currency,
allocation and external-data review remain agent responsibilities, not API mechanics.

Synthetic integration tests collect both workflows through `Dispatcher.invoke` and
`HostedClient`, including linked-page aggregation, then reconcile the existing
arithmetic helpers. They cover credit revenue and refunds separately from
allocations, draft-linked/non-billable time, day budgets, denied reads, malformed
projections, missing fields, running timers and currencies. These checks make no
live account calls; sandbox evidence and independent calculation review remain
separate gates.

## Recurring billing scenarios

`freeagent_ai.recurring.recurring_scenario` expands reviewed recurring profile
snapshots separately from this module's outstanding-invoice arithmetic. See the
[calendar, payment and generated-invoice overlap contract](recurring-revenue.md).
Its billing events are not recorded revenue or guaranteed cash. Pass only reviewed
additional commitments into forecast, keep currencies separate, and preserve the
helper's missing_inputs. Existing generated invoices stay in normal invoice reads;
never also count their profile occurrence as additional cash.
