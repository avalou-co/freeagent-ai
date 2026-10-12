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

Manage the existing tenant through `avalou-infrastructure/environments/auth0`,
prepared in [infrastructure PR #3](https://github.com/avalou-co/avalou-infrastructure/pull/3).
That CI-deployed root imports the original resource IDs and uses the existing GCS
state bucket at prefix `auth0/`. Its README provides the one-time Management API credential/bootstrap setup for
the `auth0-production` deployment environment and optional state-only diagnostics.
The main-only workflow imports and updates existing resources using a saved plan;
PR checks have no Auth0 credentials. No automation credential
or live import exists yet; do not create replacement applications or rotate their
secrets to perform this migration.

The Action JavaScript and tests remain canonical here. Infrastructure pins a
reviewed application commit and SHA-256 and stages those committed bytes before
Terraform validation/deployment. Changes go through the application review/tests,
then an infrastructure pin update reviewed in a PR; CI checks and applies the
saved plan from main. Terraform also declares the
single post-login binding, so routine deployment does not require dashboard drag
and drop. Keep state/plan files private and omit Management API key/credential
read scopes to avoid importing application secrets.

## Auth0 setup reference

The owner has created `avalou.uk.auth0.com`. Its verified issuer is
`https://avalou.uk.auth0.com/` (including the trailing slash), and its public
discovery advertises PKCE S256. The dedicated client IDs are:

- ChatGPT: `T9wZakykbNwaGDNcUdXmbtxd9VJs3yA6`.
- Account linking: `WHciYkjNGgnuasHgashUS4LLCya0iORz`.

Both clients use authorization-code grants only, database login and one-hour ID
tokens. The API has one-hour access tokens, explicit consent, no offline access,
per-app user authorization and no client-credentials access. The ChatGPT client has
exactly the two declared scopes; resource parameter compatibility is enabled.
The reviewed Action is deployed and its post-login trigger attachment was verified
in the dashboard with “All changes are live”. This is configuration evidence;
fresh login, SSO, PKCE rejection and replacement journeys still require live tests.
Its PKCE gate requires a valid S256 challenge and authorization-code flow, using
[Auth0's documented Action approach](https://support.auth0.com/center/s/article/Enforce-PKCE-with-Actions).
Secret provisioning, the exact OpenAI callback and dedicated reviewer accounts
still need to be connected to this deployment. Use an email/password
database connection. Disable social/enterprise connections for these applications
and verify free-plan eligibility and tenant region in the dashboard.

The following describes the desired configuration for verification; Terraform
is its canonical owner after import.

1. Use an API whose identifier is `https://freeagent-ai.avalou.co/mcp`. Use RS256,
   3600-second access tokens and scopes `freeagent:read`, `freeagent:write`. Enable
   Resource Parameter Compatibility Profile. Disable offline access.
2. Use the predefined confidential OAuth client for ChatGPT: authorization-code
   grant only, PKCE S256 required, no refresh grant, token endpoint authentication
   `client_secret_basic`. Enter its secret privately in OpenAI's portal; never
   add it to Terraform, the ZIP, issue text or logs. Register the exact callback
   shown by OpenAI's connection flow, not an invented callback.
3. Use the separate regular web application for linking, using authorization code
   plus PKCE. Register `https://freeagent-ai.avalou.co/auth/callback`. Configure
   one-hour ID tokens. Store its client secret as `freeagent-auth0-web-secret`.
4. Deploy the pinned `auth0/primary-auth-time.js` through Terraform as a Post Login
   Action. Supply the two public client IDs as Action secrets MCP_CLIENT_ID and
   WEB_CLIENT_ID. The Action requires
   exactly one `pwd` method timestamp, excludes refresh grants and other connections,
   and signs `https://freeagent-ai.avalou.co/primary_auth_time` on both token types.
5. Verify actual fresh login, reused SSO, multiple browsers, late code exchange and
   redirect continuations. The claim must retain the original PRIMARY login time,
   never issuance time/MFA/continuation time. Reconnection after hourly expiry must
   work in ChatGPT web, iOS and Android before release.

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
