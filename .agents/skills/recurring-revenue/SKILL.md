---
name: recurring-revenue
description: Read-only recurring invoice profiles and reviewed billing/cash scenarios.
argument-hint: "[horizon] [contact] [currency]"
---

# Recurring revenue review

Follow `docs/agent-rules.md` and [recurring scenario assumptions](../../../docs/recurring-revenue.md).
GET tools only; do not create or change profiles or issue invoices.

1. Confirm company, contact scope, currency and inclusive horizon. Record a UTC
   collection timestamp. Read company and all pages of recurring invoices separately
   with `view=active`, `view=inactive` and `view=draft`; optionally filter contact.
   Locally use `freeagent_get("recurring_invoices?view=active&per_page=100")` and the
   other views; hosted use `list_recurring_invoices` and `get_recurring_invoice`.
   A failed/denied read is incomplete, never an empty collection. Reconcile profiles
   appearing in multiple views after a status change; never count them twice.
2. Show groups separately, with profile links, provider frequency, recurring status,
   next/end dates, currency and net/tax/gross values. Inactive is a documented view,
   not an invented `recurring_status` value. Fetch selected details to review lines.
   Blank end means unbounded; absent fields remain unavailable. Leave other currencies
   in separate scenarios with visible exclusions; no automatic conversion.
3. Read complete invoices for the selected scope. Provider documentation does not
   specify a generated-invoice/profile relationship field. Do not match by contact,
   amount or date alone and call it proven. Review each billing occurrence against
   generated invoices (including Draft/Paid), existing forecast commitments and
   payments already in opening balances. Record exact date-to-invoice links or an
   explicit reviewed no-overlap decision. Unresolved overlap stops its cash inclusion.
4. Confirm the calendar scenario convention with the user: anchor date/day, independent
   month-end clamping (Jan 31 -> Feb 28 -> Mar 31), and inclusive end. These are
   scenario assumptions, not verified provider scheduling rules. Resolve a stale
   `next_recurs_on` before expansion. Ask for expected payment delay after billing;
   invoice payment terms do not establish actual collection behavior. Keep unsupported
   cadence and unavailable assumptions incomplete.
5. Run `freeagent_ai.recurring.recurring_scenario` with reviewed snapshots as described
   in the canonical doc. Active profiles alone produce future billing events.
   Inactive/Draft profiles are shown without forecast receipts. Preserve incomplete
   status and missing evidence; never silently treat missing data as zero.
6. Label billing events separately from expected cash receipt dates. Hand off only
   reviewed additional commitments to the cash-flow workflow. Existing generated
   invoices continue through normal outstanding `due_value` handling, never a second
   recurring commitment. Carry missing_inputs into the forecast and display assumption
   links, collection time, exclusions and events beyond the cash horizon. This is a
   scenario, not booked revenue or guaranteed cash.
