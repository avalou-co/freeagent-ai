---
name: documents
description: Request invoice, estimate and credit-note PDFs through secure same-account browser delivery.
---

# Accounting document PDFs

1. Establish the linked company with `get_company`. Resolve the user's selected
   document using `list_invoices`, `list_estimates` or `list_credit_notes` and the
   matching detail tool `get_invoice`, `get_estimate` or `get_credit_note`. Match
   reference/contact; ask when ambiguous. Never guess the document or company.
2. Call `get_invoice_pdf`, `get_estimate_pdf` or `get_credit_note_pdf` with the
   selected numeric ID. The tool validates provider identity and a bounded PDF,
   then supplies metadata and the registered document UI. No file bytes or
   temporary grant are visible to the model.
3. Ask the user to choose **Download PDF** in the document card. The documented
   host action opens the first-party HTTPS download page. That page requires a
   browser sign-in matching the original selected account and a second click to
   obtain the native PDF attachment. The offer expires in two minutes and works
   once. Missing host navigation support is explicitly unavailable; no invented
   file IDs, base64 prose or local-execution fallback is permitted.
4. If browser sign-in is needed, use its separate sign-in link. Signing in may
   replace account credentials, invalidating an earlier offer: reconnect in
   ChatGPT if requested and obtain a fresh offer after checking the company again.
   A different browser account cannot redeem the offer. Never change the target
   company to match that browser account or replay an expired offer.
5. Describe success only when the user/client confirms the attachment arrived.
   Tool preparation and a source fixture are not actual installed web/mobile
   evidence. Permission errors, missing PDFs and malformed/oversized responses
   are incomplete reads. Do not issue/send/change status to obtain a PDF.

If a legacy local tool returns an embedded resource instead of the registered
card, treat it as diagnostic output and report hosted delivery unavailable through
that connection. Do not claim a file arrived.

This workflow is read-only and authorizes no accounting writes. See
[delivery contract and current verification limits](../../../docs/documents.md).
