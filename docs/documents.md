# Accounting document PDF delivery

The hosted source integrates a registered MCP Apps UI with a same-account HTTPS
PDF attachment route. It replaces the experimental embedded-blob-only output.
No client interpreter, shell, filesystem, invented ChatGPT file ID or public bearer
file URL is used. Actual deployed marketplace web/mobile delivery remains an
explicit release verification gate; source/fixture success does not satisfy it.

## Documented host contract

Official OpenAI documentation checked 2026-10-29:
[registered MCP Apps UI](https://developers.openai.com/plugins/build/chatgpt-ui),
[UI quickstart](https://developers.openai.com/plugins/build/app-quickstart) and
[plugin reference](https://developers.openai.com/plugins/reference).
Tools declare `_meta.ui.resourceUri`; authenticated resources/list and
resources/read serve `ui://freeagent/document-download.html` with MIME type
text/html;profile=mcp-app. Tool result `_meta` is component-only, while text and
structuredContent contain public document metadata. The UI receives the result
through the documented MCP Apps bridge and feature-detects the optional
window.openai.openExternal method. It opens the allowlisted first-party HTTPS
receiver with redirectUrl:false after a user click. A host without that method
shows an unavailable message. This is secure browser attachment delivery, not a
claim that ChatGPT imported a file into its native file library. OpenAI's file
helpers document existing authorized file IDs; they do not establish a generic
server blob-to-file-ID conversion.

## Provider and authorization contract

Provider contracts checked 2026-10-29:
[invoices](https://dev.freeagent.com/docs/invoices),
[estimates](https://dev.freeagent.com/docs/estimates),
[credit notes](https://dev.freeagent.com/docs/credit_notes).
The documented collection/:id/pdf reads return RFC 2045 base64 in pdf.content;
minimum access is Estimates and Invoices. Named get_invoice_pdf,
get_estimate_pdf and get_credit_note_pdf verify the record URL and PDF under the
current read-scoped MCP company binding before preparing a two-minute one-use
offer. The canonical shared state store retains only the selected fixed collection,
numeric ID, original subject/company/environment/generation and expiry, never PDF
bytes. Its existing TTL cleanup and atomic consumption apply across instances.

The component-only URL carries the random offer in a fragment. The first-party
receiver clears the fragment before submitting a small POST form; fragments do
not enter HTTP request URLs, access logs or referrers. No token enters model text,
structuredContent, state cookies, analytics or local/session storage. The POST
requires exact same-origin Origin, a valid existing HttpOnly browser session and
the same original subject/company/environment/generation. A different signed-in
browser account is refused, never substituted. A missing browser login requires a
separate sign-in; reauthorization/relinking can invalidate the offer, in which
case the user must obtain a fresh one from ChatGPT.

After authorization, atomic consumption permits one redemption. The route fetches
a fresh bounded PDF using the original binding/deadline and checks that binding
again before responding with application/pdf and Content-Disposition: attachment.
A disconnect, relink, expiry, replay, wrong origin, oversized form, provider failure
or identity mismatch fails closed. HTTP errors never expose provider bodies or
file data. Responses are no-store/nosniff; attachment responses use no-referrer. The receiver
uses same-origin referrer policy so native form POST preserves its Origin header
for validation; its URL has no token after immediate fragment clearing and no
referrer is sent cross-origin. There is no persistent
byte cache, file-serving grant in a URL query/path, or background file generation.
Unused metadata expires; disconnect invalidates outstanding offers immediately.
The host/browser controls already-delivered attachment retention.

Decoded files are limited to 5 MiB and encoded strings to 8 MiB within the hosted
8 MiB JSON transport limit. Strict base64 (RFC 2045 whitespace), PDF header and EOF
checks validate the transport envelope, not a complete PDF parser or malware scan.
Safe filenames contain only the fixed collection and numeric ID. The local MCP
prototype retains embedded resources for diagnostics; hosted tools never emit
those blobs as usable client output.

## Verification and operational gates

Synthetic authenticated HTTP and browser integration tests cover the registered
UI, private result metadata, native PDF attachment headers/body, original account
binding, session/origin checks, malformed/oversized input, expiry, concurrent
replay and revocation. They do not prove current production routing or installed
ChatGPT web/iOS behavior. Before claiming delivery, independently review the
artifact/security contract, deploy the reviewed source and verify a sample PDF
from each document type in the actual installed web and mobile client, including
wrong-browser-account, expired offer and reconnect journeys. Record client/version,
reviewed source SHA and observed attachment results separately in private
operational evidence. Retain existing request-body/access-log redaction and avoid
logging tool-result _meta, browser form bodies or response contents.
