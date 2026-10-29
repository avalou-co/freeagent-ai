---
name: payroll
description: Read-only UK payroll periods, filing status and provider payment obligations, without employee payslips.
argument-hint: "[tax year end] [period]"
---

# Payroll evidence

Follow `docs/agent-rules.md` and [payroll evidence rules](../../../docs/payroll.md).
Read only. Never run payroll, file, pay, or change paid/unpaid status.

1. Ask for the company, tax year end and requested period/as-of date. Use
   `get_company` to confirm the linked company. UK payroll support and at least
   Tax and Limited Accounting access are required; authorization does not prove
   company support. Do not inspect employee details for a company filing review.
2. Call `list_payroll_periods(year=...)`. Year is the tax year end: April 2025
   through March 2026 uses "2026". The result includes all linked periods and
   payment obligations. Use `get_payroll_period(year=..., period=...)` only for
   a selected provider period identifier from that result; do not guess it from
   calendar month numbers. Period detail deliberately omits employee payslips.
3. Show returned source URLs, collection timestamp, pay date, frequency, period
   and filing status. Preserve unfiled, pending, rejected, partially_filed and
   filed states. Filing does not establish payment. Show annual payment evidence
   separately: due_on, amount_due and status exactly as returned; do not attribute
   an annual payment to an individual period without provider evidence.
4. Preserve zero/negative amounts and missing fields. Omitted payment status is
   unavailable, not proof of payment. marked_as_paid is a provider marker, not
   independently verified bank settlement. No currency is documented on payroll
   responses: use only an explicit provider/company currency context and label
   its source, or disclose that the payment currency is unavailable.
5. Distinguish successful empty collections from missing, malformed, unsupported
   or denied reads. Explain successful records alongside failures, without
   claiming complete coverage. Multiple years require separate selected reads.
   Do not calculate totals, residual debt, tax, forecast commitments or dates.
   If an amount, status, employee detail or requested metric is unavailable,
   say so; never infer a substitute or expose unrelated employee information.
6. Re-read if the user needs a current snapshot. No payment, filing, status-change
   or payroll-execution operation is part of this workflow. Use named remote
   tools on web/iOS; no client-local runtime is required.
