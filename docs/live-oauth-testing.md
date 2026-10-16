# Test the production service with your own account

The production deployment includes read and write tools. Start with the read-only
connection checks below, then approve only accounting changes you intend to make.
Your account does not prove two-company isolation or public directory publication. Do not enter credentials or tokens in chat or GitHub.

## Before starting

After the owner merges the reviewed production-access infrastructure PR, CI
enables the backend. Publishing the static website alone does not do that. Confirm
OAuth discovery and a missing-token MCP response of 401 after deployment. A 403 from Google is not an application OAuth challenge.

The owner must configure the exact callback displayed by ChatGPT in Terraform's
`openai_callbacks`, and supply the dedicated ChatGPT application's client secret
privately in ChatGPT's connection configuration. Do not guess a callback or use
the separate Account Linking or Management API client's credentials.

## Link and read

1. Open https://freeagent-ai.avalou.co/account. Create/sign in to the application's
   email/password account through Auth0. This is separate from the Auth0 dashboard
   administrator account. Link your FreeAgent company and confirm the displayed
   company is yours. Enter FreeAgent credentials only on FreeAgent's login page.
2. Sign in again when prompted after linking. Fresh primary authentication after
   the link commit is required; an older login must not gain access to a new link.
3. In ChatGPT, open Plugins, choose the plus button, then **Add custom MCP server**.
   Use the name FreeAgent AI and https://freeagent-ai.avalou.co/mcp. Configure OAuth
   with the dedicated client, review the displayed permissions and create the
   plugin. Complete sign-in and consent. The connection must request
   `offline_access` before claiming automatic renewal works; capture only redacted
   pass/fail evidence, not tokens or callback URLs containing codes.
4. Start a new chat, select the plugin using `@`, and ask: “Show my company name
   and invoice statuses. Do not create or modify anything.” Compare the company
   and a few invoice references/statuses with FreeAgent. Do not paste their data
   into public evidence.
5. Leave the connection for more than the one-hour access-token lifetime, then
   repeat the read. It should renew without a new primary login while within the
   30-day absolute session limit. Record any sign-in prompt or provider error.

## Disconnect and reconnect

Disconnect on the application's account page, then repeat the read in the old
ChatGPT connection. It must be denied. Reconnecting requires linking if needed,
a fresh primary login after the disconnect/replacement commit, and new MCP
authorization. The old connection must not silently revive.

Two separate sample companies and users are required to verify company replacement,
cross-user access denial and approved financial writes. Your one company cannot
establish those results. Use dedicated sample data before testing writes.

Repeat the successful read/disconnect journey in ChatGPT web, iOS and Android
where the connection is available. Record unavailable features as unverified,
not passed. Do not confuse a private connection with a published directory app.

Official setup: https://developers.openai.com/plugins/deploy/connect-chatgpt
OAuth/callback contract: https://developers.openai.com/plugins/build/auth


## Accounting operations on your live company

The complete toolset is enabled, but no write is authorized by connecting or
by this deployment request. Supply the exact records/details you want, inspect
the proposed change, approve it explicitly, and compare the readback with FreeAgent.
Use draft invoices/estimates and verify their status and automatic-email settings.
Only correct/delete entries created during that request after separate approval.
On timeouts or failed readback, inspect the existing record before retrying.
Receipt uploads remain unavailable until verified download hosts are configured.
