# Receipts

Use `/freeagent-ai:receipts` for evidence-based extraction and review. Extraction
runs in the assistant that can read the uploaded image/PDF; the MCP server does
not contain an OCR service. Unknown fields block creation until resolved. Existing
expense and bill tools encode attachments and return a FreeAgent readback.

FreeAgent documents a 5 MB attachment limit and PNG/JPEG/GIF/PDF support for
[expenses](https://dev.freeagent.com/docs/expenses) and
[bills](https://dev.freeagent.com/docs/bills). PDF is documented as
`application/x-pdf`. The tools pass provider accounting validation through.
Both creation helpers accept optional `currency`; omitting it retains provider
defaults. Receipts must use explicit reviewed currency. Tax amounts, multiple
rates or other fields outside convenience parameters require an approved direct
API payload; do not approximate the document to fit a helper.

## Hosted upload contract

This is the contract for hosted attachments coordinated with #36, not a claim
that an upload storage service or server-side OCR is deployed.

Existing public tools accept OpenAI file references (`download_url`, `file_id`,
optional `mime_type`, `file_name`), not filesystem paths. They require an
authenticated principal, write scope and `confirmed=true`, bind the account before
downloading, and attach only within that invocation. Downloads require HTTPS and
an operator allowlisted host, public DNS addresses pinned to the connection, no
redirect following, identity encoding, bounded time and a 5 MB streaming cap.
The new type check accepts only PNG/JPEG/GIF/PDF signatures and normalizes MIME
metadata before sending to FreeAgent. No receipt bytes or signed URLs are stored
by the application; bytes exist in request memory until the invocation ends.
Assistant platform and FreeAgent attachment retention are separate policies.

Any future persistent upload service must meet these requirements before release:

- Bind upload, inspection, retrieval and deletion to authenticated subject AND
  original company; opaque file IDs alone never authorize retrieval. Deny
  cross-account reuse, stale bindings and access after disconnect. Never cache
  file references or extracted contents across subjects or companies.
- Accept at most 5,000,000 bytes per document and a bounded request/batch size;
  validate actual signatures, declared MIME and safe filenames. Enforce parser
  page, pixel, decompression, memory and time limits before extraction. Reject
  encrypted, corrupt, unsupported and active-content documents when safe parsing
  is unavailable. Use isolated parsers with no network or credential access.
- Encrypt stored content, use short-lived account-bound references, and delete
  originals, derivatives and extracted text within 24 hours or immediately on
  user deletion/disconnect. Document backup expiry and deletion failures.
  Do not log bytes, document text, personal data or signed URLs. Audit only opaque
  operation IDs, owner checks and outcome. Do not expose internal storage URLs.
- Treat embedded text and links as untrusted. Extraction never authorizes writes.
  Preserve the reviewed source association through approval and creation; refresh
  expired references from the same user and recheck the source before use.
- Verify two-account isolation, oversize/type spoofing, parser resource exhaustion,
  expiry, deletion and secret-free errors independently before enabling storage
  or extraction. Existing invocation-only downloading does not prove all of these.

The current downloader has no parser, persistent object store, file-ID ownership
lookup or 24-hour deletion worker. Its signed source URL is a bearer capability;
source platform authorization and user-provided file association remain required.
A host allowlist alone does not establish account ownership. Do not enable a
persistent upload service until the contract and independent review pass.
