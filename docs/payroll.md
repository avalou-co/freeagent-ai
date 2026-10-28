# Payroll evidence

The [FreeAgent payroll API](https://dev.freeagent.com/docs/payroll), checked
2026-10-28, provides UK RTI payroll periods and payment evidence. Minimum provider
access is **Tax and Limited Accounting**, and the company must support payroll
in FreeAgent. The integration does not infer eligibility from company type or
reproduce payroll validation. Provider denials and unsupported company responses
remain errors, never empty/zero evidence.

`list_payroll_periods(year)` reads the fixed `payroll/:year` endpoint. The year is
the tax year end (April 2025–March 2026 uses 2026). Both `periods` and `payments`
collections are required, and shared transport follows linked pages. Missing or
malformed collections fail as incomplete. Missing fields within a record stay
absent rather than receiving invented defaults.

`get_payroll_period(year, period)` reads fixed `payroll/:year/:period`. Choose the
provider's period identifier from the year result (documented as 0–11), rather
than calculating a period from a month. The provider detail endpoint includes
employee payslips; this workflow projects **only period metadata**, deliberately
omitting all payslips, user references, tax codes and compensation details.
Neither response is logged or persisted by these adapters. Existing authenticated
transport binds each call to the original user's linked company.

The tools return provider period URLs and an explicit request `source_url`, plus
a UTC `collected_at` timestamp. Period fields preserve frequency, pay date,
filing status, Employment Allowance/CIS fields and provider timestamps where
returned. Payments preserve due date, signed amount and status. The annual
payment collection is not a per-period payment allocation; do not join those
records by guessed dates. Missing status remains unavailable. A provider
marked_as_paid flag does not prove bank settlement, and filed does not mean paid.
Payroll responses do not document a currency field: identify an explicit company
currency as context or report unavailable payment currency, without silently
labelling an amount GBP. No residual, aggregation, payroll calculation or forecast
is supplied.

Both operations are read-only, require `freeagent:read`, accept no destination or
write payload, and expose no employee payslip tool. Execution, filing, payment and
mark-paid/unpaid transitions remain unavailable, including the provider's
state-changing GET route. Employee-specific questions are outside this workflow.
Do not place payroll data in logs, screenshots, public artifacts or shared files.

Synthetic authenticated HTTP and package tests verify provider requests,
projections, authorization, company isolation, incomplete responses and privacy.
They do not establish live UK company support, actual assistant decisions,
sandbox/provider behavior or installed marketplace web/iOS evidence. Those remain
separate verification gates; no live payroll writes are authorized.
