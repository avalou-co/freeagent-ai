---
name: cash-flow
description: Read-only 13-week cash forecast with payment-delay and custom commitment scenarios.
argument-hint: "[start date] [account scope] [currency]"
---

# Cash forecast

Follow `docs/agent-rules.md` and `docs/analysis.md`. GET tools only.

1. Confirm start date matching the UTC snapshot date for current balances, selected business accounts, currency and account assignment
   of future receipts/payments. Ask for payroll, tax and recurring commitments;
   explicitly confirm none or list missing inputs. Do not infer bill payment accounts.
2. Read `bank_accounts`, `invoices?view=all&per_page=100`, `bills?per_page=100` and `credit_notes?per_page=100`. Review outstanding
   credit-note refunds as signed outgoing commitments; do not assume allocations
   are cash refunds or count allocated credits twice.
   Automatic pagination aggregates pages once. Stop on incomplete/failed reads.
   Record UTC collection timestamp and each account's latest activity date.
3. Select outstanding records for scope. Use `current_balance` and `due_value`,
   not invoice totals or historical bank transactions. Reconcile unexplained
   payments already reflected in balances but still outstanding on invoices/bills.
   Exclude internal transfers within scope. External transfers need reviewed signed
   commitments. Keep currencies separate; no automatic conversions.
4. Normalise additional commitments with unique evidence `url`, `date`, `currency`,
   signed decimal `amount` (payment negative), `additional: true`. Confirm no overlap
   with balances or outstanding API records. Expand recurrence into dated occurrences
   with unique evidence IDs and parent links. Never invent inputs.
5. Run `freeagent_ai.analysis.forecast` with reviewed snapshots and `missing_inputs`.
   Compare `receipt_delay_days=0`, a user-chosen delay, and custom commitments.
   See docs/analysis.md for keyword arguments. Local arithmetic makes no API calls.
6. Show 13 weekly opening/receipts/payments/closing amounts with source links,
   timestamp/activity dates, overdue records, exclusions, missing inputs, events
   outside the horizon and first negative opening/closing week. An overdue receipt
   is assumed at start plus delay, not promised. Positive weekly closing balances
   can hide shortfalls within the week. Incomplete forecasts remain provisional.

## Hosted collection

Use the fixed `list_*`/`get_*` tools in
[the field coverage table](../../../docs/analysis.md#hosted-field-coverage).
Omit `page` and leave `paginate=true` for complete collections. A denied, failed or
invalid read is incomplete data, never an empty collection or zero. Report the
failed operation and stop the calculation until resolved. Preserve helper
`status="incomplete"` and missing-input/rate evidence in the result.
Read `list_credit_note_reconciliations` as allocation evidence alongside
`list_credit_notes`. Review outstanding signed `due_value` refunds separately;
confirm payment date, account, currency and overlap before adding a commitment.

Tax commitments may come from the tax-overview workflow only after review of
taxpayer scope, residual amounts, dates, currency and overlap with opening balances,
bills and existing commitments. Filing deadlines are never payment dates.
