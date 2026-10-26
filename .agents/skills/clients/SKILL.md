---
name: clients
description: Find or create FreeAgent contacts, projects and tasks. Use when the user asks to set up a new client or project, or resolve client/project names before logging time or invoicing.
---

# Clients workflow

Read [agent rules](../../../docs/agent-rules.md) and [API notes](../../../docs/api-notes.md) before writing. The business supplies contact details, payment terms, currency, rates and budgets; ask for missing details rather than inventing defaults.

Use named remote tools in ChatGPT web/iOS. Contact lookup uses `list_contacts`
with view=all and matching returned identity fields; a failed lookup is not proof
that a contact is missing. No local executor or client filesystem is required.

1. **Find the contact first.** Call `list_contacts` and inspect selected details with
   `get_contact`. Compare known organisation/person names and email in the returned
   records; ask the user to select ambiguous identities. Reuse the selected provider
   URL inside nested payloads and numeric IDs for top-level tool parameters.
2. **Resolve project and tasks.** Call `list_projects` for the selected contact and
   `list_tasks` for the selected project, using their declared view filters. Inspect
   details with `get_project` / `get_task` when needed. Check inactive records too;
   ask whether to use an existing entry or create a distinct one. Never change an
   existing record to make it fit, or infer absence from an incomplete read.
3. **Collect only the missing setup details.** A new contact needs an organisation name or both first and last name; confirm supplied email/address and payment terms. If payment terms are omitted, explain that FreeAgent applies its defaults and get approval for that choice. A new project needs name, currency, `normal_billing_rate` as a decimal string and explicit `billing_period` (`hour` or `day`). If budgeted, confirm `budget` and `budget_units` (`Hours`, `Days` or `Monetary`); otherwise confirm no budget. Each new task needs name, `billing_rate` as a decimal string and explicit `billing_period`. Do not silently use the tools' day/Days defaults or assume task rates equal project rates.
4. **Preview and obtain approval.** Show the contact to reuse or create, the project and tasks to reuse or create, payment terms, currency, rate amounts and periods, and budget/units. Obtain a clear yes before creation unless the user already supplied these exact details and instructed you to proceed. Approval to set up a client does not authorize logging time or creating an invoice.
5. **Create in parent order.** Call `create_contact` only if needed, then `create_project` with the verified numeric contact ID, then `create_task` with the verified numeric project ID. Pass the approved rate periods and budget units explicitly. Each tool returns a readback; check the stored values and parent relationship before creating children. When reusing an existing contact/project, repeat the relevant duplicate lookup just before creation if setup has taken time. If new matches appear, resolve them before writing.
6. **Report and hand off.** List the contacts, projects and tasks reused or created, their URLs, and the terms/rates/currency/budget FreeAgent holds. Stop on a mismatch, failed readback or uncertain write; inspect existing records before retrying, and report partial completion. Do not recreate a parent that already succeeded. Offer the [timesheets](../timesheets/SKILL.md) or [invoicing](../invoicing/SKILL.md) workflow if the user wants to continue, collecting its missing details and approval.

For corrections, follow the shared [task correction rules](../../../docs/agent-rules.md#correcting-entries-created-in-the-current-task). Never modify or delete entries created outside this request.
