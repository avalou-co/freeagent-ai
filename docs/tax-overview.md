# Tax return evidence and cash-flow handoff

Read-only workflow; FreeAgent remains the accounting authority. No tax rates,
liabilities, filing transitions or payment execution are calculated or submitted.

Official contracts checked 2026-10-25:

| Tax | Collection | Detail | Provider documentation |
| --- | --- | --- | --- |
| VAT | `vat_returns` | `vat_returns/:period_ends_on` | https://dev.freeagent.com/docs/vat_returns |
| Corporation Tax | `corporation_tax_returns` | `corporation_tax_returns/:period_ends_on` | https://dev.freeagent.com/docs/corporation_tax_returns |
| Income Tax | `users/:user_id/self_assessment_returns` | same collection plus `/:period_ends_on` | https://dev.freeagent.com/docs/income_tax_returns |

Local `freeagent_get` accepts these paths; hosted tools are the six named
list/get operations in the tax-overview skill. Dates are ISO period-end dates,
not numeric IDs. Income Tax requires an explicit numeric user ID. No arbitrary
path or unsupported filing/payment operation is added to the hosted inventory.
All reads require the provider's Tax, Accounting & Users access; company type,
VAT registration, available tax functionality and user permissions determine actual
availability. A non-UK/unsupported company, permission denial or failed endpoint
is unavailable coverage, not evidence of no liabilities. Successful empty lists
mean only that this endpoint returned no records at collection time.

VAT/Income Tax expose nested payments with label, due_on, amount_due and status.
Corporation Tax exposes amount_due, payment_due_on and payment_status directly.
Filing deadlines/statuses are separate. Missing payment status is documented for
zero/negative payments; positive missing status is unresolved. marked_as_paid is
provider bookkeeping evidence, not independently verified bank settlement. paid is
reserved by the current provider contract. Partial-paid balances are not exposed;
never invent remaining debt from a binary unpaid marker. Show pending/rejected/
provisionally_filed exactly, without treating them as successful filing.

The projections retain source URLs, periods, filing evidence and payment fields;
VAT breakdown boxes are outside this workflow. Tax amounts do not carry a currency
in these contracts: confirm the applicable tax denomination with the taxpayer;
company currency alone is not proof of personal tax currency. Preserve that explicit
currency through the forecast; no exchange-rate assumptions or cross-currency sum.
For personal tax, also confirm that the selected business account should fund it.

The skill owns review and overlap decisions. One return may contain several
payments on different dates. Distinguish each occurrence by return URL + payment
index and keep the parent source visible. The same obligation in a bank balance,
bill or prior commitment must not be counted twice. Payment-on-account/balancing
credit interactions need review, not blind netting. Exact partial residuals and
refund dates need evidence/user confirmation. Past-due amounts need reconciliation
with opening balances and a reviewed future payment date. Filing dates never
substitute for payment dates. Unresolved inputs flow into forecast missing_inputs.

Verification uses synthetic dispatcher/HostedClient fixtures and reviewed forecast
commitments. No live sandbox, tax authority filing state or real payment acceptance
has been verified. Before claiming live availability, check a dedicated authorized
sample account for applicable company/user types and provider field behavior.

## Review examples (synthetic, not live execution evidence)

- A UK limited company with VAT registration: review VAT and Corporation Tax;
  read personal self-assessment only for a separately selected authorized user.
- A UK sole trader: review VAT if registered and the selected user's
  self-assessment. Do not invent a Corporation Tax return for that taxpayer.
- A partnership or other company type: confirm which taxpayer each return belongs
  to; do not infer partners' personal returns from the company alone.
- A company with unavailable tax functionality: report the failed/unsupported
  coverage explicitly, even if another tax endpoint succeeds. Do not predict
  obligations from country/type or grant access on that basis.
- An unpaid 120 payment with 40 already reflected in the bank balance: hand off
  only a reviewed remaining 80 payment, not the full 120 or an invented status.
  The synthetic dispatcher-to-forecast test verifies this 80 maps to an outgoing
  payment without counting the 40 twice. That test supplies the review decisions;
  it does not establish autonomous judgment or provider partial-payment tracking.
