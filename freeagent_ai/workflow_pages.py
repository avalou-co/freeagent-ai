"""Public workflow explanations based on the packaged, reviewed agent workflows."""

import html
from typing import NamedTuple


class Workflow(NamedTuple):
    title: str
    description: str
    introduction: str
    prompt: str
    sections: tuple[tuple[str, str], ...]


WORKFLOWS = {
    "timesheets": Workflow(
        "Log FreeAgent timesheets with your assistant",
        "Prepare FreeAgent time entries in ChatGPT or Claude, review dates, projects, tasks and hours, then approve each entry before it is recorded.",
        "Use FreeAgent AI to prepare time entries for a specific day or date range. Tell your assistant which client, project and task the work belongs to, who did the work and how many hours to record. Your time records stay in FreeAgent.",
        "Help me prepare last week's timesheets. Show me the available projects and tasks, check existing entries, and ask me for the hours before recording anything.",
        (
            (
                "Start with the work you actually did",
                "Supply the dates and hours rather than asking your assistant to invent a working week. If a project or task name is ambiguous, review the available choices. Setting up a missing client, project or task is a separate action that needs your approval.",
            ),
            (
                "Check existing entries before adding time",
                "Your assistant reads the relevant timeslips and flags possible overlaps. A failed lookup does not mean the week is empty. Resolve a possible duplicate before creating another entry, especially if you have already logged time in FreeAgent.",
            ),
            (
                "Approve the exact entries",
                "Review the date, person, project, task, hours and comment for each proposed timeslip. After you approve, your assistant records the entry and checks what FreeAgent returned. If the result is uncertain, inspect the existing record before trying again.",
            ),
        ),
    ),
    "invoicing": Workflow(
        "Prepare draft FreeAgent invoices",
        "Review invoice details and eligible project work with FreeAgent AI, then approve a draft invoice without sending it to your customer.",
        "Use FreeAgent AI to prepare a draft invoice from your instructions and the records in your FreeAgent account. Start with the client, optional project and invoice date, then choose manual line items or a supported project-source workflow.",
        "Help me prepare a draft invoice for a client. Ask which client and work to include, check existing invoices, and show me the proposed details before creating it.",
        (
            (
                "Bring the details your invoice needs",
                "Confirm the client, date, currency, payment terms, reference and bank account. For manual lines, supply descriptions, quantities, prices and tax treatment. Your assistant asks about missing details rather than treating previous settings as permission to reuse them.",
            ),
            (
                "Review which work will be included",
                "Project-source inclusion can cover groups of eligible records rather than individual items. Your assistant must inspect the relevant project evidence and explain the scope. If exact inclusion cannot be established, narrow the request before approving it. FreeAgent determines eligibility and calculates invoice amounts.",
            ),
            (
                "Create a draft for review",
                "Approve the proposed invoice details before creation. Your assistant checks the returned draft, lines, currency and provider totals. Automatic emails stay off. Creating a draft does not send the invoice, mark it paid or authorize a later status change; review and complete those actions in FreeAgent.",
            ),
        ),
    ),
    "expenses-and-bills": Workflow(
        "Review FreeAgent expenses and supplier bills",
        "Prepare expense claims and supplier bills with reviewed receipt details, duplicate checks and approval before creating FreeAgent records.",
        "FreeAgent AI helps you prepare expense claims and supplier bills from the information you provide. Tell your assistant what the purchase was for and whether you need an expense claim or a supplier bill. It asks about missing business details before proposing a record.",
        "Help me review this purchase for FreeAgent. Ask whether it is an expense claim or supplier bill, check for duplicates, and show me the exact proposed record before saving it.",
        (
            (
                "Choose the right kind of record",
                "An expense claim and a supplier bill use different details. For a claim, confirm the claimant, date, amount, currency and category. For a bill, identify the supplier, reference, bill and due dates, and line items. Supply the business's tax treatment; the assistant does not choose VAT rules for you.",
            ),
            (
                "Review the source and possible duplicates",
                "Where supported by the connected assistant, a receipt image or PDF can provide evidence for a proposal. Unclear text or missing amounts need your review. Existing expenses and bills are checked for possible matches before creation. A failed or incomplete lookup is not duplicate clearance.",
            ),
            (
                "Approve and check what was saved",
                "Review the exact dates, references, categories, amounts, currency, tax fields and any attachment before approving. FreeAgent validates the record and provides the returned amounts. Your assistant compares the saved result with the proposal and flags missing evidence or differences rather than silently retrying an uncertain creation.",
            ),
        ),
    ),
    "estimates": Workflow(
        "Prepare FreeAgent estimates and quotes",
        "Prepare a draft estimate, quote or proposal in FreeAgent with reviewed client details, line items and approval before creation.",
        "Use FreeAgent AI to prepare a draft estimate, quote or proposal for a client. Describe the work and supply the commercial details you want to offer. Your assistant resolves the contact and optional project, then shows the proposed document for review.",
        "Help me prepare a draft quote for a client. Ask for the client, scope, line items, currency and reference, then show me the plan before creating it.",
        (
            (
                "Choose the document and its scope",
                "Say whether you need an Estimate, Quote or Proposal. Confirm the intended contact and project so the document belongs to the right client. If there is more than one matching name, select the returned record rather than relying on a guess.",
            ),
            (
                "Supply the line items",
                "For each line, provide the description, unit, quantity and price, along with the currency and reference. Ask your assistant to surface missing details before you approve. FreeAgent handles the accounting validation and returns the document amounts; your assistant does not invent prices or calculate a separate tax total.",
            ),
            (
                "Review the returned draft",
                "After you approve the exact plan, the document is created as a draft. Your assistant checks the returned document type, status, lines, currency and amounts against your instructions. It does not send the estimate to your client. Review the draft in FreeAgent before deciding what to do next.",
            ),
        ),
    ),
    "invoice-status": Workflow(
        "Check FreeAgent invoice status and overdue payments",
        "Read outstanding and overdue FreeAgent invoice records, inspect returned due amounts and draft chase wording without sending reminders.",
        "Ask FreeAgent AI which invoices are outstanding or overdue, or check a specific client's invoices. This workflow reads the records held by FreeAgent and can prepare chase wording for you to review. It does not send reminders or change invoices.",
        "Show this client's overdue invoices with references, due dates, currencies and amounts due. Do not send reminders or change anything.",
        (
            (
                "Choose the client and records",
                "Name a client or specify the status and date range you want to review. Your assistant resolves the contact and reads the relevant invoice pages, opening details where needed. If the provider cannot filter by the requested date, it explains how the returned records were selected.",
            ),
            (
                "Read the recorded payment position",
                "Review each returned invoice's reference, dates, status, total and amount due, with its currency and source link. These values describe FreeAgent's records. Your assistant does not infer bank settlement, combine currencies or treat missing payment information as a zero balance.",
            ),
            (
                "Prepare a chase you can send",
                "If you want a follow-up, supply the tone, wording and timing your business uses. Your assistant can draft the message for you to review and send yourself. A request to check status or draft wording does not authorize sending, marking an invoice paid or changing its status.",
            ),
        ),
    ),
    "bank-reconciliation": Workflow(
        "Review unexplained FreeAgent bank transactions",
        "Inspect unexplained bank transactions in FreeAgent, review proposed invoice or bill matches, and approve explanations one item at a time.",
        "Use FreeAgent AI to review unexplained transactions in a selected FreeAgent bank account. Your assistant compares the returned transaction details with invoices, bills and your business's category instructions, then proposes explanations for you to check.",
        "Show the unexplained transactions for my selected bank account. Suggest possible matches, label uncertainty, and wait for my approval for each explanation.",
        (
            (
                "Select the account and inspect the evidence",
                "Choose the bank account when more than one is available. Your assistant reads the unexplained transactions and relevant open invoices or bills. Compare the contact, reference, dates, currency and provider amounts before deciding that a payment belongs to a particular record.",
            ),
            (
                "Resolve uncertain matches",
                "A similar amount is evidence to review, not proof of a match. Your assistant labels uncertain suggestions and asks for your category or matching rules when they are missing. It does not invent an accounting category or treat an unsuccessful lookup as confirmation that no matching record exists.",
            ),
            (
                "Approve each explanation",
                "Review the proposed explanation for each selected transaction before authorizing it. After saving, your assistant reads back what FreeAgent holds and reports any amount left partly unexplained. Existing explanations are not edited or deleted by this workflow. If a write has an uncertain result, inspect the original transaction before another attempt.",
            ),
        ),
    ),
    "reports": Workflow(
        "Read FreeAgent reports with your assistant",
        "Read FreeAgent profit and loss, balance sheet, trial balance, bank balances and overdue records for the dates you choose.",
        "Ask FreeAgent AI to retrieve and explain the financial reports returned by FreeAgent. Choose a profit and loss report, balance sheet or trial balance, or review bank balances and overdue invoice or bill records. This workflow is read-only.",
        "Show my FreeAgent profit and loss for a date range I will provide. Keep the provider's labels and amounts, show the report dates, and explain any unavailable information.",
        (
            (
                "Specify the period you want to see",
                "Confirm the company and dates rather than assuming financial-year boundaries. A profit and loss or trial balance uses a date range; a balance sheet uses an as-at date. Bank balances are current snapshots and should be read with their returned activity dates and currencies.",
            ),
            (
                "Keep the report tied to its source",
                "Your assistant presents FreeAgent's report values, signs, labels and currencies, along with the requested period and available source links. Overdue invoices and bills are separate provider records. Missing amounts or failed endpoints remain unavailable evidence rather than becoming zero values or an empty report.",
            ),
            (
                "Understand the limits of the result",
                "This is a view of the records FreeAgent returns, not a new accounting calculation or a custom cash forecast. Your assistant does not derive fresh tax, margin or budget figures from incomplete evidence. Reviewing a report does not change records, make payments, submit filings or send reminders.",
            ),
        ),
    ),
}


def workflow_links(current: str | None = None) -> str:
    return (
        '<ul class="workflow-guide-links">'
        + "".join(
            f'<li><a href="/workflows/{slug}/">{html.escape(workflow.title)}</a></li>'
            for slug, workflow in WORKFLOWS.items()
            if slug != current
        )
        + "</ul>"
    )


def render_workflow(slug: str, asset_prefix: str) -> str:
    workflow = WORKFLOWS[slug]
    escape = html.escape
    canonical = f"https://freeagent-ai.avalou.co/workflows/{slug}/"
    sections = "".join(
        f"<section><h2>{escape(title)}</h2><p>{escape(body)}</p></section>" for title, body in workflow.sections
    )
    return (
        '<!doctype html><html lang="en-GB"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(workflow.title)} | FreeAgent AI</title>"
        f'<meta name="description" content="{escape(workflow.description, quote=True)}">'
        f'<link rel="canonical" href="{canonical}">'
        f'<link rel="stylesheet" href="{escape(asset_prefix, quote=True)}site.css">'
        f'<link rel="icon" href="{escape(asset_prefix, quote=True)}favicon.svg" type="image/svg+xml">'
        '</head><body><a class="skip-link" href="#main">Skip to content</a>'
        '<main id="main" class="notice workflow-guide">'
        '<nav aria-label="Breadcrumb"><a href="/">FreeAgent AI by Avalou</a></nav>'
        f'<article><h1>{escape(workflow.title)}</h1><p class="guide-introduction">{escape(workflow.introduction)}</p>'
        "<section><h2>Try asking your assistant</h2>"
        f"<blockquote><p>{escape(workflow.prompt)}</p></blockquote></section>{sections}</article>"
        '<section class="guide-access"><h2>Using FreeAgent AI</h2>'
        "<p>These guides describe the workflows for a connected UK FreeAgent account. "
        "Available connections depend on your assistant and service access. "
        '<a href="/#connection">Check how to connect</a> or <a href="/support/">contact support about access</a>.</p></section>'
        '<nav class="guide-related" aria-label="More workflow guides"><h2>Explore other workflows</h2>'
        + workflow_links(slug)
        + '</nav><footer><a href="/privacy/">Privacy</a> · <a href="/terms/">Terms</a> · '
        '<a href="/support/">Support</a></footer></main></body></html>'
    )
