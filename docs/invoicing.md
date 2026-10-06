# Invoicing workflow (draft only)

Generic. The consuming repo supplies contact, project, bank account, reference format, payment terms and delivery rules.

1. Check the period's timeslips are complete and not already billed (compare against earlier invoices' line dates).
2. Read the latest invoice for the project to copy reference style, terms, bank account and settings.
3. `POST invoices` with `include_timeslips: "billed_grouped_by_timeslip"`, all `send_*_emails: false`, and no placeholder items (see `api-notes.md`).
4. `GET` the invoice and verify status `Draft`, line count, totals and emails off.
5. Report reference, due date, lines and totals. Say the reference number is an assumption if you inferred it.

Never send, mark as sent or email an invoice unless the user explicitly asks in that conversation.
