# Hosted service

FreeAgent AI's public service origin is https://freeagent-ai.avalou.co.
The hosted service exposes authenticated tools for FreeAgent reads and writes.
Directory publication, supported client platforms and live provider verification
are separate from deployment.

## Runtime configuration

Install `pip install -e '.[hosted,dev]'`. `freeagent-ai serve` starts the ASGI
application on `$PORT` (default 8080). Required configuration must be present before
startup. Hosted requests never use local credential files or an operator token.
Local stdio and shared-token HTTP are separate development transports.

Configure these values privately in the operator's deployment system:

| Environment variable | Purpose |
| --- | --- |
| GOOGLE_CLOUD_PROJECT | Project containing the connection store |
| AUTH0_ISSUER | HTTPS Auth0 tenant origin, including trailing slash |
| AUTH0_MCP_CLIENT_ID | Dedicated assistant OAuth client |
| AUTH0_WEB_CLIENT_ID | Separate account-linking client |
| AUTH0_WEB_CLIENT_SECRET | Account-linking client secret |
| FREEAGENT_CLIENT_ID / FREEAGENT_CLIENT_SECRET | Upstream OAuth application |
| FREEAGENT_ENVIRONMENT | `production` or `sandbox`; use separate upstream applications |
| FREEAGENT_TOKEN_ENCRYPTION_KEY | Encryption keyring, provisioned outside source/state |
| OPENAI_FILE_DOWNLOAD_HOSTS | Verified exact upload download hosts; empty denies downloads |
| OPENAI_DOMAIN_CHALLENGE | Plain-text challenge supplied by the publishing portal |

Keyring format: `{"active":"1","keys":{"1":"<base64 32-byte key>"}}`.
Use random keys. Retain old decrypting keys until old connections have been safely
refreshed, relinked or re-encrypted. Never commit secrets, user data, actual deployment
identifiers or operator runbooks to this public repository.

## OAuth and sessions

Keep assistant authorization separate from upstream FreeAgent account linking.
Use RS256, the service's `/mcp` audience, exact callback allowlists and PKCE S256.
The full service supports `freeagent:read` and `freeagent:write`. Write operations
also require explicit confirmation of the exact plan and readback afterward.
Deployment itself does not authorize accounting mutations.

Only the assistant client accepts refresh grants. Intended access/ID token lifetime
is one hour, with rotating refresh families bounded by a 30-day absolute lifetime
and idle lifetime one second shorter; infinite lifetimes and reuse leeway are off.
Request `offline_access` before claiming automatic renewal works. Account linking
remains code-only with a one-hour browser session.

The canonical `auth0/primary-auth-time.js` Action uses separately configured
MCP_CLIENT_ID and WEB_CLIENT_ID values. It requires database primary authentication
and preserves the original password authentication time in server-owned refresh
metadata. Missing/malformed/expired metadata denies renewal; it must never substitute
current time or a later login. The resource server separately enforces that original
30-day limit. Verify metadata capability and propagation on the real tenant.

Disconnect/replacement advances a connection generation and server cutoff timestamp.
Old credentials cannot bind to the replacement company or revive after renewal.
Reconnecting requires fresh primary authentication after the commit. Timestamp
equality denies access. In-flight writes may already have completed: inspect before
retrying. Disconnect is not accounting rollback.

Account callbacks use single-use state, PKCE, nonce and a Secure/HttpOnly/SameSite=Lax
session cookie. Account actions also require exact Origin and a one-use action token.
Dynamic responses are no-store. OAuth callback URLs can contain authorization codes:
protect platform request logs as well as application logs before live callbacks.
Never log authorization headers, signed file URLs or accounting payloads.

## Production deployment and testing

Persistent cloud/identity configuration and operational records belong in the
operator's private deployment repository. Public application CI builds content and
images; private infrastructure CI deploys reviewed image digests. The owner reviews
and merges PRs. Do not apply infrastructure or change identity settings ad hoc.

Review the public connected-service Privacy/Terms/Support content in `landing.py`
before inviting account linking. Application CI publishes website content after
merge. Hosted policy routes use the same notices. Build the reviewed main image
through the existing CI workflow, then hand its digest to private deployment CI.

Complete [the live test guide](live-oauth-testing.md) after deployment. Confirm
resource discovery and anonymous MCP 401 with its OAuth challenge. A Google IAM
403 is not an application OAuth challenge. Obtain the exact assistant callback
from its management page; generic documentation examples are not actual callback
values. Configure callbacks privately through Terraform.

Verify fresh authentication, account identity, reads, individually approved writes
and readback, renewal beyond one hour, disconnect denial and fresh-auth reconnect.
Two sample users/companies are needed to verify isolation; one company cannot prove
it. Provider rotation/reuse, absolute expiry, receipt uploads and web/iOS/Android
behavior remain unverified until actually tested. Empty download hosts deny receipt
uploads; ordinary writes do not require attachments. Backups are optional; keep
operator cost/recovery decisions in private runbooks.

## Tools and publication

The public tool registry and audit live in `public_tools.py`. Export descriptors:

```sh
python -c 'import json; from freeagent_ai.public_tools import audit; print(json.dumps(audit(), indent=2))'
python -m freeagent_ai.public_package --draft --output build/freeagent-ai-draft.zip
```

Draft packages are review artifacts. They contain canonical workflows and named
tools, without arbitrary API execution, local file readers or operator credentials.
Provider accounting/model validation remains FreeAgent's responsibility. Requests
have shared deadlines, bounded downloads and per-subject rate limits. Reads fail
rather than presenting partial pagination as complete; writes are not retried after
uncertain outcomes. Failed readback preserves the known created resource for recovery.

Public listing requires publisher/domain verification, approved public policies,
reviewer access, real review-case evidence, assets, platform verification and owner
publication. Use `publication/review-cases.md` with dedicated sample accounts. Keep
reviewer credentials, customer information and operational evidence outside this
public repository. Do not equate a private connection or successful deployment with
an approved directory listing.
