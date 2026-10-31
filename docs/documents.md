# Accounting document PDF delivery

The registered document card identifies an invoice, estimate or credit note and
provides one Download PDF action. That action obtains fresh authorization through
the host's authenticated MCP bridge, opens a transient first-party browser route
and starts a native HTTPS PDF attachment automatically. It requires no second
confirmation, browser cookie, separate login, client interpreter or invented file
ID. It is browser delivery, not a claim of a native ChatGPT attachment. Actual
installed web/mobile acceptance remains a release gate.

## Host contract

Official OpenAI documentation checked 2026-10-29:
[registered MCP Apps UI](https://developers.openai.com/plugins/build/chatgpt-ui),
[UI quickstart](https://developers.openai.com/plugins/build/app-quickstart) and
[plugin reference](https://developers.openai.com/plugins/reference).
The card is registered at ui://freeagent/document-download-v2.html using
_meta.ui.resourceUri and authenticated resources/list/read. Component-only result
_meta contains an opaque original-context handle; text and structuredContent have
only document metadata. On the user's action, the MCP Apps tools/call bridge invokes
a UI-only refresh operation with no output template, so it does not create another
card. The result contains a fresh private URL for documented openExternal navigation
with redirectUrl:false. A host lacking required support shows an inline error.

The openExternal API does not document a browser-open or file-arrival
acknowledgment. The card reports only that it requested the browser download;
an explicit host rejection remains an inline error. A resolved call, including a
host no-op, does not prove that a browser opened or that a PDF arrived. A native
browser Save dialog is normal file handling. User-confirmed file arrival and
first-action behavior remain separate client evidence; a later successful action
does not establish that the first one succeeded. No navigation is retried
automatically; another user action refreshes authorization and obtains a new grant.

The file APIs document uploadFile for user-selected files and download helpers for
already authorized file IDs. They do not establish that a backend PDF blob becomes
a native ChatGPT attachment or how to mint such an ID. This flow does not rely on
that assumption, a local executable, or an unverified upload-and-render fallback.

## Original authorization and delegated capability

Provider contracts checked 2026-10-29:
[invoices](https://dev.freeagent.com/docs/invoices),
[estimates](https://dev.freeagent.com/docs/estimates),
[credit notes](https://dev.freeagent.com/docs/credit_notes).
Each documents collection/:id/pdf with RFC 2045 base64 at pdf.content and minimum
access Estimates and Invoices. Named PDF tools verify record identity and a bounded
PDF through the current read-scoped company binding. The display label uses the
provider reference when returned; filenames retain only the fixed collection/ID.

The canonical state store retains an immutable context containing the original
subject, company, environment, generation, fixed collection/ID and authorization
window. This context is not download authority. It lasts only within the original
connected-session limit (up to the existing 30-day window), so a card open for hours
does not depend on an expired two-minute offer. Every refresh requires current
verified MCP read scope and an exact original subject/company/environment/generation
and document-type match. A new account with the same numeric document ID cannot
silently replace the original selection. Original bindings are checked before and
after provider fetches. Relinking, disconnection or authorization expiry fails
closed; refreshed access does not extend the original context window.

A successful user-initiated refresh mints a separate random 256-bit, one-file,
120-second single-use delegated capability. Possession of that token authorizes
only its original selected document; this is an explicit narrow bearer authority,
not browser identity authentication. A copied token could be redeemed during that
short window. It remains private to the component, appears only in a URL fragment
and then a small POST body, and never enters model text, structuredContent, HTTP
URL paths/queries, logs, referrers, cookies or browser storage. The static inline
bridge clears the fragment before further requests and automatically submits the
bounded POST. Its script is pinned by a CSP hash. No manual receiver form is shown.

Redemption ignores browser cookies: an absent or different browser account cannot
substitute provider credentials. It uses only the original MCP-authorized binding,
requires exact first-party Origin, rate limits the original subject, atomically
consumes the capability before a fresh provider read, and rechecks revocation before
releasing bytes. Expired, replayed, revoked or uncertain outcomes do not yield files.
A retry in the existing card obtains a new authorized capability; it does not replay
a used one. This removes document-specific OAuth/browser-session coupling.

The state store retains metadata only, with canonical TTL cleanup; no PDF bytes,
persistent file cache or background generation are stored. The response is
application/pdf with Content-Disposition: attachment, no-store and nosniff. The
attachment uses no-referrer. The transient bridge uses same-origin referrer policy
to preserve the native form Origin header; its fragment is already gone, and no
cross-origin referrer is sent. No API response body, grant or file data is logged.
The host/browser controls retention of already received files.

Hosting applies CSP and referrer overrides only to static website paths. Dynamic
document routes retain the backend's response-specific headers: the receiver's
exact script hash and same-origin referrer policy, and the attachment's
no-referrer policy. A global Hosting override would block the receiver script or
remove the Origin evidence required by the download POST. Browser regression
tests include Hosting's global response-header overlay; deployment checks must
also inspect the final public receiver headers.

Decoded files are limited to 5 MiB, encoded strings to 8 MiB, within the hosted
8 MiB JSON transport bound. Strict base64, header and EOF checks validate the
transport envelope, not a complete PDF parser or malware scan. Legacy local
embedded resources remain diagnostics and are not advertised as usable output.

## Verification limits

Synthetic HTTP and Chromium desktop/mobile-viewport tests exercise the full normal
OAuth transaction, signed MCP authorization, registered card, one user action,
automatic native PDF attachment, stale-card refresh, absent/different browser
cookies, denied/cross-account refresh, relinking, expiry, revocation and atomic
replay/concurrency guards. They do not prove production routing or actual installed
ChatGPT web/iOS delivery. Independent review, deployment of the reviewed source and
actual installed-client attachment results for each document type remain #72
acceptance gates. Record that evidence separately in private operational records.
The publication builder stays blocked while those observations are pending;
draft/operator candidates do not assert acceptance or public availability.
