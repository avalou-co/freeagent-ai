# API notes

Paths are relative to `https://api.freeagent.com/v2/`. Pass resources as full URLs and amounts as strings.

## Projects and tasks

- Find existing ones with `GET projects?contact=<contact url>&view=active` and `GET tasks?project=<project url>&view=active` before creating.
- `POST projects`: `{"project": {"contact", "name", "status": "Active", "currency", "normal_billing_rate", "billing_period"}}`. Add `budget` and `budget_units` (`Hours`, `Days` or `Monetary`) for a budgeted project.
- `POST tasks?project=<project url>`: `{"task": {"name", "status": "Active", "billing_rate", "billing_period"}}`. The project goes in the query string, not the body. `billing_period` is `hour` or `day`.

## Timeslips

- `POST timeslips`: `{"timeslip": {"task", "project", "user", "dated_on", "hours"}}`.
- `GET timeslips?from_date=&to_date=&per_page=100` returns one page. Check it for dates that already have a timeslip.
- A per-day task bills a full day's hours as one day. Check the task's `billing_period` and rate first.

## Invoices

- `POST invoices` with `project`, `contact` and `include_timeslips: "billed_grouped_by_timeslip"` adds the project's unbilled timeslips as lines. FreeAgent bills each timeslip once.
- Do not add a placeholder `invoice_items` entry as well. FreeAgent adds it as an extra line and the total comes out too high.
- New invoices are `Draft`. Set `send_new_invoice_emails`, `send_reminder_emails` and `send_thank_you_emails` to `false`.
- To remove a line, `DELETE invoice_items/<id>`. A `PUT` with `_destroy` did not work.
- Past invoices (`GET invoices?project=...`, then `GET invoices/<id>`) show the reference format, terms, description style and VAT to copy.
- Check after creating: status, line count, net = quantity × rate, VAT, emails off.

## Estimates

- `POST estimates`: `{"estimate": {"contact", "dated_on", "currency", "status": "Draft", "estimate_items": [{"description", "item_type", "quantity", "price"}]}}`. `project` is optional.
- Estimates have no email flags. Sending is a separate action this repo never takes.
- `GET estimates?contact=...` (or `?project=...`) shows the reference style to copy.
- Converting an approved estimate into an invoice is not supported yet.
- Check after creating: status, line count, net = quantity × price.

## Expenses

- `POST expenses`: `{"expense": {"user", "category", "dated_on", "gross_value", "description"}}`. `gross_value` includes VAT and is negative for a cost (`"-12.50"`).
- `GET expenses?from_date=&to_date=` finds duplicates.

## Bills

- `POST bills`: `{"bill": {"contact", "reference", "dated_on", "due_on", "bill_items": [{"category", "description", "total_value", "sales_tax_rate"}]}}`. `total_value` is the line's net before VAT.
- `GET bills?view=open` lists unpaid bills and `GET bills?view=overdue` overdue ones.
- `GET bills?from_date=&to_date=` finds an existing bill with the same reference.

## Shared by expenses and bills

- `sales_tax_rate` (e.g. `"20.0"`) sets VAT. The category has to allow VAT.
- `GET categories` lists categories. Use the admin expenses ones for expense claims.
- Attachments: `attachment: {file_name, content_type, data}` with `data` in base64. FreeAgent takes PDF, PNG, JPG and GIF up to a size limit, and the tools allow only those types.

## Contacts

- `POST contacts`: `{"contact": {...}}` with `organisation_name`, or `first_name` and `last_name`. Address fields are `address1`, `town`, `postcode` and `country`. Payment terms go in `default_payment_terms_in_days`.
- `GET contacts?view=all&per_page=100&page=N` lists contacts. The API has no name search, so `find_contacts` filters the list itself.

## Errors

Rate limits and server errors raise `urllib.error.HTTPError`. The response body usually names the problem.
