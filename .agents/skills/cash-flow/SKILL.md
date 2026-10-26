---
name: cash-flow
description: Read-only FreeAgent bank balances and outstanding invoice, bill and credit records.
argument-hint: "[account scope] [currency] [as-of date]"
---

# Cash balances and outstanding records

Follow [agent rules](../../../docs/agent-rules.md) and
[provider evidence coverage](../../../docs/analysis.md). Read only.
The skill identifier is retained for compatibility; this workflow does not forecast cash.

1. Confirm company, selected business accounts, currency and requested date scope.
   Use `get_company` and `list_bank_accounts`; use `get_bank_account` for a selected
   account. Show the provider's current_balance, currency, latest_activity_date,
   status and source URL with collection time. Current balances are not historical
   balances for an arbitrary as-of date; explain that limitation.
2. Read `list_invoices`, `list_bills`, `list_credit_notes` and
   `list_credit_note_reconciliations` for the requested record scope. Fetch details
   with `get_invoice`, `get_bill`, `get_credit_note` or
   `get_credit_note_reconciliation` when needed. Omit page and retain paginate=true
   for complete collections. A failed or denied read is unavailable coverage,
   never an empty list or zero balance.
3. Show each record's provider dates, status, currency, total_value, due_value,
   paid_value or refunded_value where returned, with its source link. Preserve
   signed credit values. A reconciliation is an allocation, not a cash payment;
   paid_value and marked-paid evidence do not prove bank settlement. Keep separate
   currencies and missing fields visible; do not derive residual balances.
4. Explain what the returned balances and records establish and which requested
   fields or periods are unavailable. Do not assign payment accounts, infer future
   receipt dates, expand recurrence, create commitments or calculate projected
   balances, cash shortfalls or payment-delay scenarios. No forecast endpoint is
   exposed by this workflow; state that forecasts are unsupported.
5. Offer invoice-status or bank-reconcile for a selected follow-up. Any subsequent
   write uses that workflow's exact preview, approval and readback rules.

Use the named remote tools above in ChatGPT web/iOS. No Python import, script,
terminal, local file or client calculator is required. Explain provider results;
do not replace unavailable FreeAgent functionality with custom calculations.
