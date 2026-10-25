# Recurring invoice visibility and scenarios

Provider contract checked 2026-10-25 against the official
[recurring invoice API](https://dev.freeagent.com/docs/recurring_invoices).
Local generic GET remains available; hosted fixed `list_recurring_invoices` and
`get_recurring_invoice` reads preserve profile identity, contact/project references,
frequency, recurring status, next/end dates, currency, exchange rate, net/tax/gross
values, payment terms and line items. List filters are `view` and `contact`; hosted
contact IDs expand to provider URLs. Pagination uses the shared complete-read path.
The documented API has no profile create/update/delete operations; none are added.

Views are active/inactive/draft. Documented recurring_status values are Active and
Draft; do not fabricate an Inactive status field. Keep membership evidence from
separate views. A duplicate URL across groups is an inconsistent snapshot requiring
reconciliation. Inactive and Draft profiles never become expected cash receipts.

## Reviewed scenario calculation

`freeagent_ai.recurring.recurring_scenario` is local arithmetic, with no API calls.
Its keyword inputs are start/end (`date`, inclusive horizon up to ten years),
timezone-aware timestamp, currency, profiles_by_view (exactly active/inactive/draft
lists scoped to one currency), complete invoice snapshots, reads_complete, and
assumptions keyed by profile URL. Each assumption contains:

- `anchor`: reviewed cadence anchor ISO date, on/before next_recurs_on. For monthly
  cadences it preserves the chosen day independently in each month, clamping only
  where needed. It must actually generate the provider's next date.
- `end_inclusive: true`: explicit agreement to the scenario end-date convention.
- `payment_delay_days`: reviewed integer >=0 after billing; missing means no cash
  commitment. Provider terms can be evidence for discussion, never assumed receipt.
- `additional_dates`: ISO billing dates explicitly reviewed as additional to all
  generated invoices, balances and existing commitments.
- `generated`: map from billing date to an existing invoice URL, reviewed as the
  occurrence's actual invoice. The snapshot must contain that invoice, same currency
  and billing date. An edited/differently dated invoice needs manual reconciliation;
  do not bypass the incomplete result with a guessed relationship.

These are user/agent review inputs, not undocumented provider fields or independent
proof of overlap clearance. The API does not document a profile-link field on generated
invoices. Matching date/contact/amount alone cannot establish the relationship.
Every occurrence must be explicitly covered by generated or additional_dates;
unknown or conflicting evidence remains incomplete. An already-generated invoice is
excluded from recurring commitments regardless of status; the cash workflow reads
its actual due_value and status separately. Never add it again as recurring revenue.

The scenario holds the selected profile snapshot gross amount constant across occurrences.
Future price, tax, exchange-rate or profile changes are not predicted; refresh and
review changed profiles before relying on a later scenario.

Supported cadence names are Weekly, Two Weekly, Four Weekly, Monthly, Two Monthly,
Quarterly, Biannually, Annually and 2-Yearly. Weekly intervals use fixed seven-day
weeks. Monthly/yearly intervals use the reviewed anchor; Feb 29 annual scenarios
return to Feb 29 in leap years, and Jan 31 monthly scenarios return to Mar 31 after
February. The provider docs enumerate frequencies but do not promise this calendar
algorithm or end inclusivity. Confirm these assumptions; do not claim a future
provider invoice will necessarily follow them. Finite end dates cap the expansion.
A stale next date, unsupported frequency or missing required fields remains incomplete.

Output contains status, timestamp, currency, groups of source URLs, billing events,
additional cash commitments and missing_inputs. Events distinguish billing_date from
expected_receipt_date; generated events retain the existing invoice link. Scenario
commitments have unique per-occurrence URLs, parent profile links, signed decimal-string
amounts, currency, expected receipt date and additional=True. Pass reviewed commitments
to `analysis.forecast`; propagate missing_inputs. Negative amounts remain signed and
require review as refunds, not ordinary receipts. No FX conversion is performed.
Provisional complete-snapshot occurrences may be shown alongside missing inputs,
but an incomplete result must never be advertised as a complete forecast. A failed
collection suppresses all commitments; it is not zero recurring revenue.

## Verification limits

Synthetic tests exercise actual authenticated hosted dispatch/pagination and local
calendar/overlap/payment arithmetic, including leap years, month ends, finite bounds,
view exclusions, currency scope, denied reads and generated invoice suppression.
They do not establish live provider scheduling rules, deployed client availability,
real cash collection or observed assistant behavior. Authorized dedicated sandbox
read verification remains a release gate. No live financial writes are needed or
performed; the workflow and added tools are read-only.
