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
| AUTH0_WEB_CLIENT_ID | Optional connection-management client |
| AUTH0_WEB_CLIENT_SECRET | Connection-management client secret |
| AUTH0_FREEAGENT_CONNECTION_SECRET | Dedicated confidential Auth0 bridge credential; empty disables the new bridge during staged deployment |
| FREEAGENT_CLIENT_ID / FREEAGENT_CLIENT_SECRET | Upstream OAuth application |
| FREEAGENT_ENVIRONMENT | `production` or `sandbox`; use separate upstream applications |
| FREEAGENT_TOKEN_ENCRYPTION_KEY | Encryption keyring, provisioned outside source/state |
| OPENAI_FILE_DOWNLOAD_HOSTS | Verified exact upload download hosts; empty denies downloads |
| MCP_BACKEND_HOST | Optional exact Cloud Run backend DNS hostname forwarded by the hosting proxy; no scheme, port or wildcard |
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

Users connect in ChatGPT, sign into FreeAgent and approve access, then return to
ChatGPT already connected. There is no separate Avalou signup. Auth0 remains the
MCP authorization server; its custom `freeagent` OAuth2 connection uses the hosted
`/connect/authorize`, `/connect/token` and `/connect/profile` bridge. Configure its
PKCE S256 support and enable only this connection for the two dedicated clients.
Disable cached SSO on those clients. Use `auth0/freeagent-profile.js` as its profile
script and `auth0/primary-auth-time.js` as its login Action.

The bridge exchanges FreeAgent credentials server-side and verifies `users/me`
and `company`. Identity hashes the environment, stable company ID and user URL;
it never merges users by email. FreeAgent access/refresh tokens remain encrypted
in the service, including short-lived pending records. Auth0 receives an opaque,
single-use receipt. Its authenticated Action redeems that receipt for the exact
Auth0 subject, commits the link, and signs the resulting generation and original
FreeAgent authorization time into tokens. Timestamp-only legacy login is rejected
by the Action once its bridge secret is configured.

Refresh grants retain both the original time and generation in server-owned
metadata. Missing, malformed or expired metadata denies renewal; a later login
must not renew an old family. Disconnect or a new authorization advances the
connection generation. Old access tokens and refresh families cannot acquire the
new generation. The optional management page uses the same FreeAgent sign-in;
that fresh authorization also invalidates previous connections. In-flight writes
may already have completed: inspect before retrying. Disconnect is not rollback.

The bridge requires its dedicated confidential client, exact Auth0 callback,
PKCE, single-use codes/profile tokens/receipts, and short expiry. Initial upstream
state is browser-bound using `__session`, the only cookie Firebase Hosting forwards.
Pending credentials are never placed in profile claims, browser URLs or logs.
Provider PKCE behavior, receipt propagation on repeat login, actual Auth0 renewal,
and the complete ChatGPT journey require live verification after deployment.

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

## Dedicated reviewer sandbox

The normal ChatGPT connection redirects directly to production FreeAgent. An
optional dedicated reviewer login at `/reviewer/login` uses the same Auth0 issuer,
MCP endpoint, tools and approval rules with FreeAgent's isolated sandbox OAuth/API.
There is no sandbox selector in the normal user journey.

Configure all three protected deployment inputs to enable reviewer login:

- `FREEAGENT_REVIEWER_CLIENT_ID`: separate sandbox OAuth application ID.
- `FREEAGENT_REVIEWER_CLIENT_SECRET`: sandbox application secret, from the secret store.
- `FREEAGENT_REVIEWER_COMPANY_IDS`: comma-separated sandbox company IDs permitted for review.

Partial configuration fails startup. This option requires the default environment
to be production. The reviewer first opens the supplied reviewer login URL and
signs into the dedicated sandbox company, then connects the plugin in ChatGPT
using the same browser. No separate Avalou account or MCP configuration is needed.
Sandbox users outside the configured sample companies are denied after FreeAgent
verifies their identity. Never use real customer accounts for review.

The reviewer entry creates a one-use, ten-minute server-owned browser marker.
It selects a provider, not permission to read or write accounting data. A successful
login replaces it with the normal authenticated management session; an active
sandbox account binding selects sandbox for subsequent OAuth in that browser.
The management session expires after one hour. `/login` starts an ordinary
production login. A missing, expired or disconnected reviewer session follows the
normal production path; sandbox selection never comes from callback query input.

The selected environment is retained server-side through callback, receipt
redemption and account binding. Provider credentials and refresh requests follow
the stored binding. Identities include the environment, so matching provider IDs
cannot merge production and sandbox accounts. Removing sandbox configuration
denies sandbox API use instead of sending its credentials to production.

Disclose the reviewer login URL, sandbox OAuth/API routing, sample data, any
provider differences and same-browser requirement in private Review details.
Supply stable dedicated credentials with all required permissions and no MFA or
operator intervention. The reviewer bootstrap login and ChatGPT OAuth must share
the service's browser cookie; different browsers or isolated cookie stores will
not carry the selection. Verify this handoff through the actual publisher tool
scan and ChatGPT review journey before claiming it works live. Local simulated
browser tests do not establish that OpenAI preserves this session.

Verify the full advertised toolset, refresh and isolation before submission. Keep
account credentials, company IDs, deployment configuration and operational evidence
in the private deployment repository and publisher portal. Implementation does
not establish reviewer approval or successful publication.


The hosting proxy may forward the backend hostname as `Host`. Configure that exact
Cloud Run hostname privately through `MCP_BACKEND_HOST` when needed; otherwise an
authorized MCP request can fail the SDK host check with HTTP 421. The public host
remains allowed and the public OAuth resource/audience is unchanged. DNS rebinding
protection stays enabled. Unlisted hosts and disallowed browser origins remain
rejected; `X-Forwarded-Host` does not grant trust. Never commit a real backend
hostname or private deployment identifier to this public repository.
