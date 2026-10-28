# Accounting document PDFs

Provider contracts checked 2026-10-28:
[invoices](https://dev.freeagent.com/docs/invoices),
[estimates](https://dev.freeagent.com/docs/estimates) and
[credit notes](https://dev.freeagent.com/docs/credit_notes).
Each documents a fixed GET collection/:id/pdf operation with RFC 2045 base64 in
pdf.content and minimum provider access level Estimates and Invoices.

Named tools get_invoice_pdf, get_estimate_pdf and get_credit_note_pdf first read
and verify the selected record URL through the same account-bound client, then
fetch its PDF. Hosted calls require freeagent:read, a current principal/company
binding and the existing rate/deadline/transport limits. No destination URL or
local path is accepted. Provider authorization remains authoritative. Relinking,
revocation or an identity mismatch fails the request rather than changing accounts.

The tools decode the provider response and return a standard MCP embedded binary
resource (application/pdf), alongside metadata in structuredContent and text.
Encoded content is confined to the protocol resource, never prose or metadata.
The numeric-ID filename contains no provider-supplied reference or customer name.
Both local MCP and hosted MCP use this contract; clients supporting embedded PDF
resources can display or expose their native attachment control. There is no
public download endpoint, signed URL, server file store or resource-read cache.
Bytes are held only for the invocation/response; the host controls subsequent chat
retention. Do not log tool response bodies or resource contents.

The limit is 5 MiB decoded and 8 MiB encoded, within the hosted transport's 8 MiB
JSON response bound. Strict base64 (with RFC 2045 whitespace), PDF header and final
EOF marker checks reject malformed/truncated envelopes; these are transport checks,
not a full document validator or malware scanner. Errors reveal no provider body,
file content or signed URL. Existing HTTPS security headers specify no-store.

Synthetic authenticated HTTP tests establish discovery, account-bound provider
requests, denied/revoked access, identity checks, bounds and MCP resource bytes.
They do not establish live provider PDF behavior, marketplace-installed web/iOS
viewing, or actual file delivery on those clients. Those checks and independent
security review remain release gates. If the host cannot display embedded PDF
resources, report delivery unavailable and direct the user to FreeAgent.
