# Hosted API inventory and design contract

Checked against FreeAgent documentation on 2026-10-12. `public_tools.audit()` exports
every fixed endpoint, JSON schema, permission and annotation for review and CI.
The local generic tools continue unchanged. The public dispatcher never receives
an arbitrary API destination/method and does not reproduce accounting validation.

| Resources | Public operations | Provider source |
| --- | --- | --- |
| Contacts | list/get/create/update/delete | https://dev.freeagent.com/docs/contacts |
| Projects | list/get/create/update/delete | https://dev.freeagent.com/docs/projects |
| Tasks | list/get/create/update | https://dev.freeagent.com/docs/tasks |
| Timeslips | list/get/create/update/delete | https://dev.freeagent.com/docs/timeslips |
| Invoices | list/get/create draft/update/delete | https://dev.freeagent.com/docs/invoices |
| Expenses | list/get/create/update/delete; reads retain receipt reference and original/native/manual tax evidence | https://dev.freeagent.com/docs/expenses |
| Mileage expenses | get_mileage_settings/create_mileage_expense; list/get use expenses and retain mileage/engine/reclaim fields | https://dev.freeagent.com/docs/expenses |
| Estimates | list/get/create draft/update/delete | https://dev.freeagent.com/docs/estimates |
| Bills | list/get/create/update/delete | https://dev.freeagent.com/docs/bills |
| Bank accounts/transactions | list/get | https://dev.freeagent.com/docs/bank_accounts and https://dev.freeagent.com/docs/bank_transactions |
| Bank explanations | get/create/delete | https://dev.freeagent.com/docs/bank_transaction_explanations |
| Users/company/categories | list/get, current-user/company | https://dev.freeagent.com/docs/users and https://dev.freeagent.com/docs/company and https://dev.freeagent.com/docs/categories |
| Accounting reports | P&L summary, balance sheet, trial balance summary | https://dev.freeagent.com/docs/profit_and_loss and https://dev.freeagent.com/docs/balance_sheet and https://dev.freeagent.com/docs/trial_balance |

Task DELETE is intentionally unavailable: the provider's task-deletion section
currently prints a users/:id endpoint. Request provider clarification rather than
infer a potentially destructive endpoint. Bank-explanation updates and arbitrary
status/send transitions are not exposed; no documented operation is invented.
Use the supported correction or explain the missing operation to the user.

Named helpers preserve existing Draft defaults and automatic-email disabling.
Updates send the exact provider payload unchanged and are annotated destructive;
invoice update is open-world because its email settings may affect recipients.
Bank explanation is destructive. Bounded private reads/other writes are not
open-world merely because FreeAgent is externally hosted.

Response projections contain workflow accounting fields and necessary provider
references. Signed attachment URLs/content, user email/profile details, account
numbers, authentication, debug data and timestamps are not echoed by default.
Provider-defined accounting report totals/rows are projected separately. Validate
schemas against sample accounts; mocked responses do not prove provider behavior.
For a requested field absent from the projection, say so rather than infer it.

Approval and current-request ownership remain agent responsibilities. Every public
write also requires confirmed=true as the agent's assertion; it is not independent
proof of approval. No task ledger, billing reservation or local eligibility locks
are introduced. Local generic payloads/responses remain direct API mechanics.
