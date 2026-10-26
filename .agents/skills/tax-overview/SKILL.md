---
name: tax-overview
description: Read-only tax liabilities, payment dates and filing status, with provider payment and filing evidence.
argument-hint: "[period] [company or user]"
---

# Tax overview

Follow `docs/agent-rules.md` and [tax evidence rules](../../../docs/tax-overview.md).
Read only: never file, mark paid/filed, initiate payments or change a return.

1. Confirm company, period, as-of date and intended taxpayer. Read `get_company`
   and `get_current_user`; use `list_users` to resolve a different authorized user
   explicitly. Do not assume a director's personal Income Tax belongs in company cash.
2. Select applicable returns using company type, VAT registration and user scope.
   Use `list_vat_returns`, `list_corporation_tax_returns`, and
   `list_self_assessment_returns(user_id=...)`; use only their declared arguments. Tax, Accounting & Users permission is required.
   Omit page and retain paginate=true. Report denied/unavailable/unsupported
   collections separately from a successful empty collection; never call them zero.
3. Select periods that overlap the requested period, including boundaries, plus
   payments due in it even when their return period differs. Fetch details with
   `get_vat_return`, `get_corporation_tax_return` or `get_self_assessment_return`,
   supplying period_ends_on and, for Income Tax, the authorized user_id.
4. Show source URL, return period, payment label, provider signed amount_due,
   payment due date/status, filing deadline/status and collection timestamp.
   Keep rejected, pending and provisionally filed statuses explicit; filing does
   not prove payment. A due date before as-of is overdue only for an unresolved
   positive payment; do not label a paid return overdue from its filing date.
   Preserve zero/negative amounts and missing statuses; negative is potential
   refund/balancing credit, not a guaranteed dated cash receipt.
5. Provider amount_due/status do not establish remaining debt after partial
   payments. Review supporting bank explanations and ask for the remaining amount
   and date when necessary. Missing status for a positive amount, unknown currency,
   incomplete reads or uncertain payment evidence make that liability incomplete.
   Display successful evidence alongside the failures without claiming full coverage.
6. Report provider payment evidence and uncertainty directly. Do not calculate a
   remaining liability, net refunds against payments, assign a business account,
   invent a future payment date or build forecast commitments. If FreeAgent does
   not expose a requested residual or metric, say it is unavailable. The cash-flow
   skill can display bank/outstanding-record evidence, not calculate a forecast.

Use named remote tools on ChatGPT web/iOS. No local Python, shell, filesystem,
script or client calculator is required. No custom tax/accounting engine is used.
