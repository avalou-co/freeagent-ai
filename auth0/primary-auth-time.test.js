const { test } = require('node:test');
const assert = require('node:assert/strict');
const { onExecutePostLogin } = require('./primary-auth-time');

const valid = () => ({
  secrets: { MCP_CLIENT_ID: 'mcp', WEB_CLIENT_ID: 'web' },
  client: { client_id: 'mcp' },
  transaction: { protocol: 'oidc-basic-profile' },
  request: { query: { code_challenge: 'a'.repeat(43), code_challenge_method: 'S256' } },
  connection: { strategy: 'auth0' },
  authentication: { methods: [{ name: 'pwd', timestamp: '2026-10-12T12:00:00Z' }] },
});
async function run(event) {
  const denied = [], claims = [];
  await onExecutePostLogin(event, {
    access: { deny: message => denied.push(message) },
    accessToken: { setCustomClaim: (...args) => claims.push(['access', ...args]) },
    idToken: { setCustomClaim: (...args) => claims.push(['id', ...args]) },
  });
  return { denied, claims };
}
test('only primary password time is signed for both dedicated clients', async () => {
  for (const id of ['mcp', 'web']) {
    const event = valid(); event.client.client_id = id;
    event.authentication.methods.push({ name: 'mfa', timestamp: '2026-10-12T12:05:00Z' });
    const result = await run(event);
    assert.equal(result.denied.length, 0);
    assert.deepEqual(result.claims, ['access', 'id'].map(kind =>
      [kind, 'https://freeagent-ai.avalou.co/primary_auth_time', 1791806400]));
  }
});
test('missing PKCE, plain, malformed challenge and non-code flows fail closed', async () => {
  for (const mutate of [e => delete e.request, e => delete e.request.query.code_challenge,
    e => e.request.query.code_challenge_method = 'plain',
    e => e.request.query.code_challenge = 'x',
    e => e.request.query.code_challenge = ['a'.repeat(43)],
    e => e.transaction.protocol = 'oauth2-refresh-token', e => delete e.transaction]) {
    const event = valid(); mutate(event); const result = await run(event);
    assert.equal(result.denied.length, 1); assert.equal(result.claims.length, 0);
  }
});
test('social login and missing, ambiguous or invalid password timestamps fail closed', async () => {
  for (const mutate of [e => e.connection.strategy = 'google-oauth2',
    e => delete e.authentication, e => e.authentication.methods.push(e.authentication.methods[0]),
    e => e.authentication.methods[0].timestamp = 'invalid']) {
    const event = valid(); mutate(event); const result = await run(event);
    assert.equal(result.denied.length, 1); assert.equal(result.claims.length, 0);
  }
});
test('unrelated applications are untouched', async () => {
  assert.deepEqual(await run({ secrets: { MCP_CLIENT_ID: 'mcp', WEB_CLIENT_ID: 'web' },
    client: { client_id: 'other' } }), { denied: [], claims: [] });
});
