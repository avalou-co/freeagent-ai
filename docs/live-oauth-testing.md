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

## Connect and read through ChatGPT

1. In ChatGPT, add/connect the FreeAgent AI plugin using
   https://freeagent-ai.avalou.co/mcp and the dedicated OAuth client.
2. Follow the connection prompt to FreeAgent. Sign in there and approve access,
   then return to ChatGPT. No Avalou email/password account or separate account
   linking page is required. Cancelling must return a failed connection without
   granting tools access.
3. Start a new chat, select the plugin using `@`, and ask: “Show my company name
   and invoice statuses. Do not create or modify anything.” Compare the company
   and a few invoice references/statuses with FreeAgent. Keep accounting data out
   of public evidence. Verify that a second connection completes the same journey.
4. The connection must request `offline_access` before claiming automatic renewal
   works. Leave it beyond the one-hour access-token lifetime, then repeat the read.
   Record any sign-in prompt or provider error. Never capture tokens or callback
   URLs containing codes.

## Disconnect and reconnect

Connect again from the plugin to verify a fresh FreeAgent authorization completes
without Avalou signup. Earlier authorizations must fail after the new connection
commits; token renewal must not revive them. The internal account page is optional
connection management, not an onboarding prerequisite. Its fresh FreeAgent sign-in
also invalidates previous authorizations. Disconnect there and confirm access is
denied; reconnect through ChatGPT and confirm only the new authorization works.

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
