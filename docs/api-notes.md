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
- Reading past invoices (`GET invoices?project=...`, then `GET invoices/<id>`) is the best source for reference format, terms, description style and VAT.
- Verify after creating: status, line count, net = quantity x rate, VAT, emails off.

## Bank explanations

- `GET bank_accounts` lists accounts; `GET bank_transactions?bank_account=<url>&view=unexplained` lists transactions still needing explanation.
- `POST bank_transaction_explanations` body: `{"bank_transaction_explanation": {"bank_transaction", "dated_on", "gross_value", ...}}` plus one of `category` (URL), `paid_invoice` (URL) or `paid_bill` (URL). `gross_value` carries the transaction's sign.
- Match invoices/bills by amount and contact: `GET invoices?view=open` / `GET bills?view=open`. A partial explanation may leave the transaction partly unexplained; re-read it afterwards.
- Category URLs and any VAT treatment come from the business's own instructions; never guess them.

## General

- Rate-limit and server errors raise `urllib.error.HTTPError`; the body usually names the problem.
- Always read back after a write and report what FreeAgent holds, not what you sent.
