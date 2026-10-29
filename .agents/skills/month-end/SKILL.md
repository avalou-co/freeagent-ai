---
name: month-end
description: Read-only FreeAgent month-end bookkeeping records, evidence limitations and user-selected follow-up guidance.
argument-hint: "[company] [from date] [to date]"
---

# Month-end bookkeeping review

Follow [agent rules](../../../docs/agent-rules.md) and
[month-end coverage](../../../docs/month-end.md). This review is read only.

1. Ask for the company, inclusive from/to dates, bank-account scope and optional
   contact/project. Call `get_company` to confirm the linked company; stop on a
   mismatch. Never guess a financial year or treat today's state as a historical
   month-end snapshot.
2. Call `list_bank_accounts`, then `list_bank_transactions` for each selected
   numeric bank_account ID with view=unexplained and the requested from_date/to_date.
   Call `list_bills` with view=overdue and those date filters. Call `list_invoices`
   separately with view=overdue and view=draft, using supported contact/project
   filters when selected. Invoice date filters are unavailable: retrieve the full
   scoped view, then present records whose returned dated_on falls in the requested
   inclusive range; label missing dates as unknown coverage. Explain that these
   views describe current provider status for records dated in the period, not
   what was overdue or draft at the historical closing date.
3. Call `list_timeslips` with view=unbilled and from_date/to_date; optionally pass
   project. Show hours, billed_on_invoice, timer and project/task references only
   where returned. This is the provider's unbilled view, not a promise that every
   returned entry is billable. A running timer is not final recorded time; an
   invoice link, including Draft, is linkage evidence. Do not calculate unbilled
   totals or decide billing eligibility.
4. If receipt or possible duplicate review is requested, call `list_expenses` and
   `list_bills` with the requested dates (and only supported scope filters), using
   the full views rather than only overdue bills. Use `get_expense`, `get_bill`,
   `get_bank_transaction` and `get_bank_transaction_explanation` for selected
   details; `list_bank_transaction_explanation_attachments` reads a selected
   explanation's attachment metadata. A missing attachment field is unavailable
   evidence; a returned empty attachment collection means no attached file in that
   collection, not proof no receipt exists. receipt_reference is a reference, not
   proof of an attached file. Show exact source IDs, references, dates, descriptions,
   amounts and currencies behind any possible duplicate suggestion; label it
   uncertain and ask the user to assess it. Similar values do not prove duplicate
   accounting records. Do not invent missing-receipt or duplicate flags.
5. For every list, omit page and leave paginate=true; do not fetch linked pages
   again manually. Keep each successful response's collected_at UTC completion
   timestamp, filters and source URLs with the evidence. Missing fields, denied,
   malformed or failed reads remain unavailable, not zero or a clean month. State
   which account/collection is incomplete and why. Collections are not an atomic
   snapshot; re-read changed or conflicting evidence before relying on it.
6. Present an ordered follow-up list: unexplained transactions (bank-reconcile),
   overdue invoices (invoice-status), overdue bills (bills), draft invoices and
   unbilled records (invoicing/timesheets), then receipt/possible duplicate review
   (receipts/expenses/bills). Include returned evidence, its source link and
   collection time, limitations, the relevant workflow and the user's choice.
   Do not send reminders, create records, allocate credits or correct entries in
   this review. Any chosen action starts its own workflow with exact preview,
   separate approval, ownership checks and affected-record readback; never blindly
   retry an uncertain write. Existing unrelated records stay unchanged.
7. After a chosen action completes, re-read the affected records with the named
   detail/list tools above in the original company, and repeat the relevant view
   query. Report remaining provider states, new collection time and partial errors.
   A read failure cannot establish that the issue was resolved.

No custom reconciliations, accounting checks, financial totals, budgets, margins,
forecasts or local calculation engine. Use named remote tools on ChatGPT web/iOS;
no local Python, shell, filesystem or assumed interpreter is required.
