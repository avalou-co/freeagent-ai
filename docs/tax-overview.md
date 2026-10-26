# Tax return evidence

Read-only workflow; FreeAgent remains the accounting authority. No tax rates,
liabilities, filing transitions or payment execution are calculated or submitted.

Official contracts checked 2026-10-25:

| Tax | Collection | Detail | Provider documentation |
| --- | --- | --- | --- |
| VAT | `vat_returns` | `vat_returns/:period_ends_on` | https://dev.freeagent.com/docs/vat_returns |
| Corporation Tax | `corporation_tax_returns` | `corporation_tax_returns/:period_ends_on` | https://dev.freeagent.com/docs/corporation_tax_returns |
| Income Tax | `users/:user_id/self_assessment_returns` | same collection plus `/:period_ends_on` | https://dev.freeagent.com/docs/income_tax_returns |

The six named remote list/get operations are described in the tax-overview skill. Dates are ISO period-end dates,
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
currency as a label on the evidence; do not assume exchange rates or sum unlike
currencies. Personal tax is not automatically a company liability.

Show each provider payment occurrence and its parent source separately. Do not
net balancing credits, derive partial-payment residuals, assign accounts or create
cash-flow commitments. Missing remaining-debt fields and uncertain payment status
must be reported as unavailable. Payment deadlines never become filing dates or
invented future receipt/payment dates.

Verification uses synthetic provider-response fixtures and authenticated remote
reads. It does not calculate forecasts. No live sandbox, tax-authority filing
state, actual marketplace session or real payment acceptance has been verified.
Before claiming live availability, verify authorized company/user types and
provider field behavior in a dedicated sample account.

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
- A return with a positive amount_due and partial-payment evidence: show the
  provider fields and explain that the API does not establish remaining debt.
  Do not subtract amounts or invent a revised payment date/status.
