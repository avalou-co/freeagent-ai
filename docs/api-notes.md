# API notes

Learned from real use. All paths are relative to `https://api.freeagent.com/v2/`.

## Timeslips

- `POST timeslips` body: `{"timeslip": {"task", "project", "user", "dated_on", "hours"}}` with full resource URLs and `hours` as a string.
- `GET timeslips?from_date=&to_date=&per_page=100` returns a page; filter by range and check for existing dates before posting.
- A per-day task is billed per day, so a full working day's hours equals one billable day. Check the task's `billing_period` and rate first.

## Invoices

- `POST invoices` with `project`, `contact`, `include_timeslips: "billed_grouped_by_timeslip"` pulls the project's unbilled timeslips in as lines.
  **Do not also send a placeholder `invoice_items` entry**: it is added on top as an extra line and inflates the total.
- A created invoice is `Draft`. Set all three `send_new_invoice_emails`, `send_reminder_emails`, `send_thank_you_emails` to `false`.
- Removing a line: `DELETE invoice_items/<id>` works. `PUT` with `_destroy` (`1` or `true`) did not remove it.
- Listing: `GET invoices?view=` `open_or_overdue`, `open`, `overdue`, `draft`, `paid`; filters `contact=<url>`, `from_date`, `to_date`. Payment fields `status`, `due_on`, `total_value`, `due_value`, `currency`. Paginate with `per_page=100&page=N`.
- Reading past invoices (`GET invoices?project=...`, then `GET invoices/<id>`) is the best source for reference format, terms, description style and VAT.
- Verify after creating: status, line count, net = quantity x rate, VAT, emails off.

## General

- Rate-limit and server errors raise `urllib.error.HTTPError`; the body usually names the problem.
- Always read back after a write and report what FreeAgent holds, not what you sent.
