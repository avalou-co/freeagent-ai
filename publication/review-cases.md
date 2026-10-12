# Reviewer walkthrough script (not executed against FreeAgent yet)

Use two dedicated sample companies. Never use the operator's personal account or
real customer data. Reviewer login must work without waiting for operator MFA,
email/SMS codes, magic links or private-network access. Enter credentials privately
in OpenAI's portal; record only pass/fail and redacted evidence here/GitHub.

| Positive | Sample prompt and expected behavior |
| --- | --- |
| 1. Link and report | "Show profit and loss from 1 January to 31 March 2026." Link the sample account, reauthenticate after link commit, call get_profit_and_loss and get_company; report actual dates/currency/figures. |
| 2. Invoice status | "What invoices are overdue?" list_invoices(view=overdue), resolve relevant contacts, report reference/due date/value/currency; never send chasers. |
| 3. Timesheet | "Prepare seven hours for [sample project/task/date]." Resolve user/project/task, inspect existing timeslips, preview, wait for yes, create_timeslip, verify with get_timeslip/list_timeslips. |
| 4. Drafts | "Prepare an invoice for the sample project's unbilled time and a separate quote for [provided line]." Preview and obtain approval; create_draft_invoice/create_draft_estimate, verify Draft and emails disabled. Bill the same sample timeslip again only in the sandbox to verify FreeAgent's upstream protection. |
| 5. Receipt/bill | Upload a sample receipt/PDF from ChatGPT, provide actual expense/bill details, preview and approve. create_expense/create_bill must attach the file and read back provider metadata; use safe correction/delete only for this request's entries after separate approval. |

| Negative | Expected behavior |
| --- | --- |
| 1. No approval/details | "Log these expenses" without category/user/date or a clear approval. Ask for missing inputs and show a plan; no write occurs. |
| 2. Invalid/disconnected auth | Disconnect/relink company A to B; replay pre-commit tokens and delayed callbacks. No old token/request accesses B; require post-commit primary auth. A revoked/expired token causes linking/reconnection. |
| 3. Unsafe input/uncertain outcome | Submit an untrusted/private receipt URL or induce failed create readback. Reject unsafe downloads before writing; preserve known created resource and original account, inspect without duplicate create. |

Record actual tools, exact sample prompts, expected and observed results for all
five positives/three negatives. Include bank reconciliation with an individually
approved sample transaction and readback in the walkthrough. Capture a real video
and actual web/iOS/Android screenshots, including hourly reauthorization and account
replacement. Mocked tests or this script alone are not submission evidence.
