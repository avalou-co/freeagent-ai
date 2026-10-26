# Provider recurring invoice profiles

The [official recurring invoice API](https://dev.freeagent.com/docs/recurring_invoices)
was checked 2026-10-26. Its read operations are available as fixed named hosted tools:

| Tool | Provider request | Mechanics |
| --- | --- | --- |
| list_recurring_invoices | GET recurring_invoices | Optional view/contact filters, shared automatic pagination and explicit page controls |
| get_recurring_invoice | GET recurring_invoices/:id | Numeric profile ID, fixed endpoint |

Contact inputs are numeric IDs expanded into URLs for the bound FreeAgent account's
API origin. The provider minimum access level is Estimates and Invoices; FreeAgent
retains permission enforcement. Hosted calls also require the read scope and current
account binding. Local generic GET remains unchanged, but the packaged workflow uses
named remote reads and needs no client Python, filesystem or shell.

Safe record projections preserve provider-returned identity, contact/project,
reference, frequency, recurring_status, next_recurs_on, recurring_end_date, currency,
exchange_rate, net/tax/total values, payment terms and invoice items. Missing fields
remain absent; no date, amount, status or relationship is filled in. Provider frequency
and values are displayed, never used to expand a schedule or calculate future totals.
The result envelope adds collected_at: the server's UTC read-completion timestamp,
not a provider update date or evidence of an atomic multi-page snapshot.

## View and explanation rules

Read active/inactive/draft views separately and retain each query label. Documented
recurring_status values are Active and Draft; inactive is a view, not a synthesized
status. A profile changing during pagination or between reads may appear across
views; explain the inconsistent coverage and re-read rather than assuming an atomic
snapshot. A successful empty collection differs from denied, failed or malformed
coverage. Do not present an incomplete overview as a complete one.

Show returned source links, dates and currencies with collection time. A blank
recurring_end_date is documented as recurring indefinitely; a missing next/end date
is unavailable. next_recurs_on is provider billing information and does not establish
when an invoice will be paid. No calendar/date expansion, payment-delay assumptions,
expected-cash dates, commitments, forecast totals or custom calculators are supplied.

The provider docs do not expose a generated invoice/profile relationship. The
connector therefore cannot identify generated invoices or compute overlap from
these reads. Explain that limitation instead of inferring relationships from
contact/date/value matches. The documented recurring API offers no profile
creation/update/deletion; no such mutations are added.

## Verification and limits

Synthetic tests cover packaged skill -> tools/list -> authenticated hosted HTTP
tools/call -> provider request/response -> usable profile results. Cases include
pagination, view/contact filters, status/date/value preservation, multiple currencies,
missing fields, empty collections, permission failures and malformed/provider errors.
They assert absence of recurring calculators and recurring mutation tools.

These checks verify API mechanics and source-evidence presentation, not actual
marketplace installation or observed assistant behavior. Authorized deployed
ChatGPT web/iOS and two-account verification remains separate under #36. No live
financial writes are performed. Custom recurrence/scenario code and its tests from
the earlier PR scope are removed rather than exposed through another runtime.
