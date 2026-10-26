---
name: recurring-revenue
description: Read-only FreeAgent recurring invoice profiles, returned dates, statuses and values.
argument-hint: "[contact] [view]"
---

# Recurring invoice profiles

Follow [agent rules](../../../docs/agent-rules.md) and
[provider coverage](../../../docs/recurring-revenue.md). Read only.
This workflow explains FreeAgent records; it does not calculate future billing or cash.

1. Confirm company, optional contact scope and requested views. Use `get_company`
   and `list_contacts` or `get_contact` when needed to resolve the intended contact;
   use the returned numeric resource ID, never guess it.
2. Call `list_recurring_invoices` separately with view active, inactive and draft
   when a full overview is requested. Optionally pass contact. Omit page and leave
   paginate=true to aggregate all linked pages once; do not manually fetch them again.
   Keep each query's view label and its collected_at UTC read-completion time with
   its records. A failed, denied or malformed read is unavailable coverage, not an
   empty list or zero. If any view fails, state that the overview is incomplete.
3. Fetch selected details with `get_recurring_invoice` using returned profile IDs.
   Show the source URL, contact/project references, recurring_status, frequency,
   next_recurs_on, recurring_end_date, currency, net/tax/total values, payment terms
   and invoice items exactly where returned. Absent fields remain unavailable;
   a blank end date is documented as recurring indefinitely. Do not invent a missing
   next date, currency, amount, status or contact/project relationship.
4. Present active/inactive/draft view groups separately. Inactive is a provider view,
   not an invented recurring_status value. If the same profile appears across views
   or later detail differs, explain possible changes during collection and re-read;
   the paginated overview is not an atomic snapshot. Preserve separate currencies
   and the provider's signed values; do not convert or sum them into forecasts.
5. Explain that next_recurs_on is FreeAgent's next billing date, not an expected or
   guaranteed cash receipt. Display only dates and values returned by the API. Do
   not expand recurrence, clamp calendar dates, infer payment delays, create cash
   commitments or calculate future totals. Future billing/cash scenarios are
   unsupported by these provider reads.
6. The documented API does not expose a generated invoice/profile relationship.
   State that identifying generated invoices or overlap is unavailable; do not infer
   a link from matching contact/date/amount. Do not add custom matching or accounting
   logic. Profile creation/update/deletion are not documented by this read-only API.

Use only the named remote tools above in ChatGPT web/iOS. No Python helper,
calculator, script, local file, terminal or assumed client interpreter is required.
Any separate invoice workflow retains its own read/approval/readback rules.
