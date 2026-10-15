# Hosted ChatGPT plugin

Public origin: **https://freeagent-ai.avalou.co**. The website at avalou.co can remain
in its existing deployment. Firebase Hosting fronts the dedicated FreeAgent Cloud
Run service, not the Avalou apex. Application code belongs here; all GCP resources
belong in [avalou-infrastructure](https://github.com/avalou-co/avalou-infrastructure).

## Implementation and release boundaries

Install `pip install -e '.[hosted,dev]'`. `freeagent-ai serve` starts the hosted ASGI
application on `$PORT` (default 8080). Missing configuration fails before binding;
the cloud path never uses a local credentials file or FREEAGENT_MCP_TOKEN. Local
stdio and shared-token HTTP remain separate development transports.

Public tools are frozen in `public_tools.py`. Export the descriptors and bindings:

```sh
python -c 'import json; from freeagent_ai.public_tools import audit; print(json.dumps(audit(), indent=2))'
python -m freeagent_ai.public_package --draft --output build/freeagent-ai-draft.zip
```

Draft ZIPs are review artifacts, not submission-ready releases. Skills are generated
deterministically from `.agents/skills`; the hosted appendix maps reads/corrections
to the named tools. No arbitrary API executor, local file reader, hook or credential
is included. The local manifests and package version are 0.2.0; this does not mean
a release tag, deployed endpoint or approved public listing already exists.

## Auth0 configuration as code

Manage recurring Auth0 configuration through `avalou-infrastructure/environments/auth0`,
prepared in [infrastructure PR #3](https://github.com/avalou-co/avalou-infrastructure/pull/3).
CI deploys from main using the existing state bucket at prefix `auth0/`.
The JavaScript and tests stay here; CI checks out a pinned application commit
and Terraform reads the source directly. No Action metadata or staging layer is used.

GitHub OIDC/permissions and the Management API credential are configured manually
once. Existing Auth0 resources must be imported manually before the first CI apply.
CI rejects creations/replacements and applies its checked saved plan; PR checks
have no Auth0 credentials. See the infrastructure root README for deployment inputs.

## Auth0 setup reference

The owner has created `avalou.uk.auth0.com`. Its verified issuer is
`https://avalou.uk.auth0.com/` (including the trailing slash), and its public
discovery advertises PKCE S256. The dedicated client IDs are:

- ChatGPT: `T9wZakykbNwaGDNcUdXmbtxd9VJs3yA6`.
- Account linking: `WHciYkjNGgnuasHgashUS4LLCya0iORz`.

The desired configuration keeps access and ID tokens at 3600 seconds. Only the
ChatGPT client accepts `refresh_token` grants; the account-linking client remains
code-only with a one-hour browser session. The API permits offline access with
explicit consent. ChatGPT must request `offline_access` alongside `freeagent:read`
and `freeagent:write` in its OAuth connection configuration.

1. Keep RS256 and the existing API audience, scopes, client authentication methods
   and exact callback allowlists. Initial authorization still requires PKCE S256.
2. Configure ChatGPT refresh tokens as rotating and expiring, with absolute and
   idle lifetimes of 2592000 seconds, both infinite flags false and reuse leeway
   zero. Auth0 owns rotation and family invalidation on reuse. Do not implement
   a second token endpoint or store ChatGPT refresh tokens in this application.
3. Deploy `auth0/primary-auth-time.js` from the pinned CI checkout. Set the two
   public client IDs as Action secrets MCP_CLIENT_ID and WEB_CLIENT_ID. Database
   login only; linking-client refresh grants are rejected.
4. Enable/verify refresh-token metadata in the tenant before release. The Action
   stores the original password authentication timestamp in server-owned token
   metadata and copies it unchanged on renewal. Missing, malformed, future or
   expired metadata denies renewal; old families without metadata need a fresh
   login. Never substitute current time, `iat`, user metadata or a later login.
   See [Auth0 Action API](https://auth0.com/docs/actions/reference/post-login/post-login-api-object)
   and [event reference](https://auth0.com/docs/actions/reference/post-login/post-login-event-object).
   Capability/plan availability and metadata propagation across rotation must be
   demonstrated on this tenant; mocked Action tests cannot establish them.
5. The resource server independently denies MCP access at original login + 30 days,
   even if a renewed access token has a later `exp`. The window never slides.
   Disconnect/replacement tombstones compare that same immutable login timestamp
   on every call, so renewed credentials cannot restore an old connection. A new
   primary login after replacement is required to access the new company.

### Release verification (manual; not performed by unit tests)

Do not deploy or merge as part of preparing these PRs. Review both changes together;
update both infrastructure workflow pins to the reviewed application commit.
After separately authorized deployment to a test tenant/environment:

- Verify `offline_access` consent and refresh-token issuance in the real ChatGPT
  connection. Exercise automatic renewal past one hour in web, iOS and Android;
  confirm new access tokens preserve original primary authentication time and
  remain valid for no more than one hour. Do not log token values.
- Exchange a rotated token again: expect `invalid_grant`, then confirm the newest
  token in that family also fails. Zero leeway intentionally rejects retries;
  verify ChatGPT serializes refreshes and handles uncertain exchanges safely.
- Use a short-lived test configuration to exercise absolute expiry. Verify no
  sliding extension, plus application rejection at exactly 30 days even for an
  otherwise valid JWT. Restore the reviewed lifetimes before release.
- Disconnect during renewal and replace the linked company during renewal. Old
  and renewed credentials must fail all reads/writes immediately. A fresh login
  can reach only the replacement company. Verify another user's company remains
  isolated and financial writes still require approval and readback.
- Test fresh login, reused SSO, late code exchange and redirect continuations:
  original password time must survive; a later login must never update an existing
  refresh family. Verify PKCE rejection and fail-closed metadata unavailability.

Reuse detection is Auth0 behavior: local tests cover our Action and configuration,
not Auth0's token endpoint. Complete the provider tests above before claiming the
connection is ready for release. No Management API credential or broader user
permissions are introduced for resource-server revocation.

Auth0 owns authorization-server discovery/JWKS. Our resource discovery points to
that issuer. Set issuer and client IDs in Terraform's reviewed nonsecret inputs.
Both read and write permissions are enforced by the dispatcher, not just metadata.

## FreeAgent linking and secrets

Create dedicated production and sandbox FreeAgent applications. Register
`https://freeagent-ai.avalou.co/freeagent/callback`. Set FREEAGENT_CLIENT_ID and
FREEAGENT_ENVIRONMENT to the corresponding application. Never mix sandbox and
production credentials or use the operator's personal account as reviewer data.

Provision secret values directly in Secret Manager (never Terraform secret versions):

| Runtime environment | Secret / value |
| --- | --- |
| AUTH0_ISSUER | HTTPS tenant origin, trailing slash |
| AUTH0_MCP_CLIENT_ID / AUTH0_WEB_CLIENT_ID | Separate public client IDs |
| AUTH0_WEB_CLIENT_SECRET | `freeagent-auth0-web-secret` |
| FREEAGENT_CLIENT_ID | Public upstream application ID |
| FREEAGENT_CLIENT_SECRET | `freeagent-client-secret` |
| FREEAGENT_TOKEN_ENCRYPTION_KEY | `freeagent-token-encryption-key` |

Encryption key secret format: `{"active":"1","keys":{"1":"<base64 32-byte key>"}}`.
Use cryptographically random keys, not passwords. A unique nonce and user/company/
environment/generation binding protect every encrypted record. To rotate, add a new
key version, change `active`, redeploy, and retain old keys until old records have
been refreshed/relinked or safely re-encrypted. Do not discard decrypting keys early.

Every disconnect/replacement atomically advances a generation and a server commit
timestamp. The tombstone remains after credentials are deleted. A new primary login
AFTER commit and new ChatGPT authorization are required. Timestamp equality fails
closed: wait a second and sign in again. In-flight requests keep the original company
and generation; a rotated refresh cannot revive a disconnected link. A financial
request already sent may have committed; disconnect is not accounting rollback.

## Deployment and operations

1. Review the app/container changes, CI and independent security report. Merge is
   human-owned. The main-only `Build hosted image` workflow pushes a digest to the
   existing restricted Artifact Registry repository; it cannot deploy Cloud Run.
2. Have the infrastructure owner review/bootstrap API and named-secret IAM additions.
   Extend the production root with OAuth settings, TTL and backup resources. Apply
   a reviewed digest privately first. Main infrastructure apply remains create/update
   only; bootstrap, hosting, public-access and recovery changes are human-run.
3. Apply the separate `environments/hosting` root after importing any existing Firebase
   association. It creates a dedicated site and ONLY `freeagent-ai.avalou.co` domain.
   Add the exact DNS records Terraform outputs; wait for ownership and TLS readiness.
4. Configure alert recipients, daily seven-day backups and an isolated restore drill.
   A restored database may contain previously valid links: invalidate generations/
   credentials before restoring public traffic. Database backup is not state backup.
5. Verify per-user OAuth/isolation and independent security approval before setting
   `public_oauth_ready=true` in a reviewed human apply. No public IAM toggle is performed
   by this application workflow. Set OpenAI's plain-text domain challenge input.

Firebase forwards only `__session` cookies. Account/link callbacks use a secure,
HttpOnly, SameSite=Lax opaque session cookie, single-use state, PKCE and nonce. POST
account actions require the exact Origin and a session-bound one-use action token.
All dynamic responses are no-store. Access logs are disabled to avoid callback codes;
never log authorization headers, signed file URLs or accounting payloads.

DNS, TLS, Firestore RPCs, retries, pagination and API requests share a 45-second
deadline. Cloud Run timeout is 50 seconds, below Firebase's 60 seconds. The SDK's
Firestore transaction RPC accessor is wrapped per client to bound begin/commit/
rollback as well as document reads; integration-test SDK upgrades. Reads fail rather
than claim partial pagination is complete. Writes are not retried on timeout/429.
Successful creates with failed readback expose the known created URL and original
company so recovery can inspect instead of creating a duplicate.

Receipts require live verified OPENAI_FILE_DOWNLOAD_HOSTS (exact hostnames). Empty
configuration denies downloads. Populate only after a real ChatGPT-upload test.
Downloads pin validated public DNS addresses, verify TLS hostname, refuse redirects,
use no environment proxy, and stay within 10 seconds/5 MiB decoded/7 MiB encoded.
No receipt contents persist on our server. Provider accounting acceptance remains
FreeAgent's responsibility. Per-subject tool requests are limited to 60/minute.

Retain the documented £1 gross Cloud Run spend cap and project alerts. This does not
cap Firebase, Firestore, backup, build, registry or secrets costs and may overshoot.
Do not disable shared billing or affect Fun Finds. Alert on authentication failures,
MCP/provider failures and cap enforcement without recording user accounting data.
Rollback to the previous reviewed image through Terraform; do not replay writes.

## Publication gates

Publisher verification, approved policy/support text, icons/screenshots, reviewer
accounts, real financial regressions, walkthrough recording and mobile evidence
remain owner/integration dependencies. Routes currently disclose setup pending;
they are not approved legal policies. Use `publication/review-cases.md` as the test
script. Do not mark #36 complete until the public listing and fresh-user mobile
journey actually work.

Release build: pass a private LOCAL metadata JSON containing the public MCP client ID,
`interface` image paths and true evidence fields `publisher_verified`, `policies_approved`,
`security_review_passed`, `reviewer_cases_passed`, `mobile_verified`, `domain_verified`.
Never put reviewer credentials in metadata. The builder refuses absent gates.

```sh
python -m freeagent_ai.public_package --metadata /private/path/publication-metadata.json --output build/freeagent-ai.zip
```

Enter reviewer access privately in OpenAI's portal. Upload, resolve scans, submit,
handle feedback, and have the publishing owner publish after approval. Record listing
URL, plugin ID, package version and image digest separately from submission/approval.
