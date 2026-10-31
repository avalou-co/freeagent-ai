---
name: documents
description: Request invoice, estimate and credit-note PDFs with one Download PDF action.
---

# Accounting document PDFs

1. Establish the linked company with `get_company`. Resolve the user's selected
   document with `list_invoices`, `list_estimates` or `list_credit_notes` and the
   matching `get_invoice`, `get_estimate` or `get_credit_note` detail tool. Match
   reference/contact; ask when ambiguous. Never guess the document or company.
2. Call `get_invoice_pdf`, `get_estimate_pdf` or `get_credit_note_pdf` with the
   selected numeric ID. The card identifies the document using its provider
   reference when available and has one **Download PDF** action.
3. The action refreshes authorization internally and opens a branded browser page.
   That page shows animated PDF preparation, then a ready screen with Download PDF
   and automatically requests the browser download once. The ready button stays
   available after saving/cancelling, using the received file in page memory; no
   download-complete screen or save confirmation is claimed.
   There is no second confirmation or separate browser login. Do not ask the user
   to request a new link when a card has been open for a while; its action obtains
   a fresh one-file capability under the original account context. A changed or
   disconnected account is refused rather than silently selecting another company.
4. Describe the result as a browser download, not a native ChatGPT file attachment.
   Claim arrival only after actual client/user confirmation. Missing host support
   stays unavailable, with an inline message; never invent file IDs, paste base64
   or require client code to produce the file.

The workflow is read-only and authorizes no accounting writes. Legacy local
embedded resources remain diagnostics, not supported hosted delivery. See
[delivery contract and installed-client verification limits](../../../docs/documents.md).
