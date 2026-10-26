# Provider-backed financial evidence

FreeAgent supplies accounting results and validates accounting operations. This
connector retrieves and explains those results; it does not calculate forecasts,
profitability, margins, cost rates, budget usage or future payment scenarios.
The compatibility skill names `cash-flow` and `profitability` now mean bank and
outstanding-record review, and project/billing-record review respectively.
The remediated cash-flow, profitability, reports and tax-overview workflows require
only named remote API tools, without client Python, a shell, local files or custom
calculators. This does not establish readiness of other skills: mileage (#88),
recurring invoices (#70) and package-wide enforcement (#90) have separate remediation.
Runtime engine removal is tracked separately in #94.

## Reports and scope

Use `get_profit_and_loss`, `get_balance_sheet` and `get_trial_balance` for the
provider's own report values and dates. Ask for business scope/accounting periods.
Bank current_balance is a current snapshot, not a historical balance or forecast.
Show provider labels, signs, currencies, source links and collection timestamps.
Do not manufacture a missing provider metric from other fields. Missing fields,
failed collections and denied permissions are unavailable coverage, not zero.

## Hosted field coverage

These are provider evidence fields, not inputs to a local accounting engine.
Use named remote tools, their declared filters and automatic pagination; omit page
and leave paginate=true for complete collections. Fetch details when a collection
omits needed evidence. Never turn a failed read into an empty collection.

| Evidence | Hosted operations | Provider fields and limits |
| --- | --- | --- |
| Company | `get_company` | Identity and provider settings; confirm scope |
| Cash accounts | `list_bank_accounts`, `get_bank_account` | currency, current_balance, latest_activity_date, status; absent activity date is unknown freshness |
| Invoices | `list_invoices`, `get_invoice` | project/contact, dated_on, due_on, status, currency, net_value, total_value, due_value, paid_value; settlement values are not period bank cash |
| Bills | `list_bills`, `get_bill` | dates/status/currency, due_value, net/tax/total values, project/rebilling and bill_items; do not compute allocations or residuals |
| Credits | `list_credit_notes`, `get_credit_note` | signed net/tax/total/due/refunded values, status, dates, items; preserve provider signs and unknown refund timing |
| Allocations | `list_credit_note_reconciliations`, `get_credit_note_reconciliation` | credit_note, invoice, dated_on, currency, gross_value, exchange_rate; allocation is not a cash refund |
| Projects | `list_projects`, `get_project` | contact, currency, budget, budget_units, hours_per_day; show these without deriving remaining budget |
| Tasks | `list_tasks`, `get_task` | project, is_billable, currency, billing_rate, billing_period, status; view=all includes inactive records |
| Recorded time | `list_timeslips`, `get_timeslip` | project/task/user, dated_on, hours, billed_on_invoice, timer.running/start_from; linked Draft invoices are still links and running time is not final |
| Expenses | `list_expenses`, `get_expense` | project, dated_on, currency and native/transaction net/tax values; preserve currency basis rather than deriving costs |
| Tax | Named return list/get tools in [tax-overview](tax-overview.md) | Provider periods, payment/filing dates, signed amount_due and status; unavailable residuals remain unavailable |

Credit-note filters include view, contact, project, updated_since, sort and
nested_credit_note_items; reconciliation filters include from_date/to_date and
updated_since. Resource filters accept numeric IDs, expanded by the server into
account-bound provider URLs. Date filtering not supported by an endpoint is an
explicit selection of retrieved records, not a fabricated provider filter.

The reconciliation detail example uses a plural root; the connector normalizes
supported response roots without changing the provider's accounting values.

## Verification limits

Synthetic tests exercise authenticated HTTP discovery and named provider-backed
reads, projections, pagination and failures. They verify transport and faithful
response availability, not an independent accounting model, assistant behavior or
actual marketplace installation. Authorized deployed web/iOS/account-isolation
verification remains separate. No live financial writes are implied.
