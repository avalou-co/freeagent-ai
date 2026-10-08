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

## Expenses

Unverified against the live API (written from the FreeAgent docs, not yet tried); confirm on first real use.

- `POST expenses` body: `{"expense": {"user", "category", "dated_on", "gross_value", "description"}}` with full resource URLs and `gross_value` as a string including VAT. Expenses are probably negative (`"-12.50"`): check the sign on an existing expense.
- `sales_tax_rate` (e.g. `"20.0"`) sets VAT; the category may need to allow it.
- Receipt: `attachment: {file_name, content_type, data}` with `data` base64. Believed to accept PDF, PNG, JPG, GIF with a size limit; the tool allows only those types.
- Categories: `GET categories`; admin expenses categories are the ones valid for expense claims.
- Check `GET expenses?from_date=&to_date=` for duplicates before posting.

## Bills

Unverified against the live API (written from the FreeAgent docs, not yet tried); confirm on first real use.

- `POST bills` body: `{"bill": {"contact", "reference", "dated_on", "due_on", "bill_items": [{"category", "description", "total_value", "sales_tax_rate"}]}}` with full resource URLs and decimal strings. Whether `total_value` is net or gross, and the sign convention, need checking against an existing bill.
- `sales_tax_rate` (e.g. `"20.0"`) sets VAT per line; the category may need to allow it.
- Attachment: `attachment: {file_name, content_type, data}` with `data` base64. Believed to accept PDF, PNG, JPG, GIF with a size limit; the tool allows only those types.
- Unpaid and overdue: `GET bills?view=open` and `GET bills?view=overdue` (view names unverified; also try `bills?view=open_or_overdue`).
- Categories: `GET categories`. Check `GET bills?from_date=&to_date=` for the same reference before posting.

## General

- Rate-limit and server errors raise `urllib.error.HTTPError`; the body usually names the problem.
- Always read back after a write and report what FreeAgent holds, not what you sent.
