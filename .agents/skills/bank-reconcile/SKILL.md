---
name: bank-reconcile
description: List unexplained FreeAgent bank transactions and suggest explanations (match to invoices or bills, or categorise). Use when the user asks to reconcile, explain or categorise bank transactions.
argument-hint: "[bank account]"
---

# Bank reconcile workflow

Generic. The business supplies which bank account to use, its categories, and any matching rules. Ask for them or find them in the business's own instructions; never guess a category.

1. `freeagent_get bank_accounts` and pick the account (ask if unclear).
2. `freeagent_get 'bank_transactions?bank_account=<url>&view=unexplained&per_page=100'`.
3. For each transaction, propose one explanation: an open invoice (`invoices?view=open`) or bill (`bills?view=open`) matching amount and contact, else a category from the business's instructions. Mark low-confidence matches as guesses.
4. Show the proposals as a table and get a clear yes per item. Never batch-approve unless the user says so.
5. For each approved item, call `explain_bank_transaction`. Report what FreeAgent holds from the read-back, and any transaction left partly unexplained.

Only explain transactions the user approved; do not edit or delete existing explanations. See `docs/api-notes.md` and follow `docs/agent-rules.md` throughout.
