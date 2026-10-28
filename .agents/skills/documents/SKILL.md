---
name: documents
description: Retrieve provider invoice, estimate and credit-note PDFs as authenticated embedded MCP resources.
---

# Accounting document PDFs

1. Ask which linked company, document type and record the user wants. Call
   `get_company`, then resolve the selected record with `list_invoices`,
   `list_estimates` or `list_credit_notes`. Match the reference/contact and ask
   when ambiguous; never guess a record ID.
2. Call `get_invoice_pdf`, `get_estimate_pdf` or `get_credit_note_pdf` with the
   selected numeric ID. The tool verifies provider identity, fetches the PDF under
   the same account binding and returns an embedded MCP `application/pdf` resource
   plus source, safe filename, byte size and collection time.
3. Present the embedded resource using the host's supported resource viewer or
   attachment control. Do not paste base64, invent a URL, ask the user to run code,
   or claim the document reached them when the host cannot display the resource.
   Report unsupported client delivery explicitly. Actual marketplace web/iOS
   resource viewing requires separate client verification.
4. Treat permission errors, unavailable PDFs, identity mismatches and malformed or
   oversized responses as incomplete reads. Ask the user to select another record
   or retrieve it in FreeAgent; do not change document status to obtain a PDF.

This workflow is read-only. It does not send email, issue documents or approve any
accounting action. Files can contain sensitive customer data: limit access to the
user-selected document. The service persists no document bytes or download URLs;
chat/host retention is controlled by the host. See [transport limits](../../../docs/documents.md).
