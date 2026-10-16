const { test } = require('node:test');
const assert = require('node:assert/strict');
Date.now = () => Date.parse('2026-10-15T12:00:00Z');
const { onExecutePostLogin } = require('./primary-auth-time');

const valid = () => ({
  secrets: { MCP_CLIENT_ID: 'mcp', WEB_CLIENT_ID: 'web', TEST_SUBJECTS: '["auth0|tester"]' },
  user: { user_id: 'auth0|tester' },
  client: { client_id: 'mcp' },
  transaction: { protocol: 'oidc-basic-profile' },
  request: { query: { code_challenge: 'a'.repeat(43), code_challenge_method: 'S256' } },
  connection: { strategy: 'auth0' },
  authentication: { methods: [{ name: 'pwd', timestamp: '2026-10-12T12:00:00Z' }] },
});
async function run(event, refreshToken) {
  const denied = [], claims = [], metadata = {};
  await onExecutePostLogin(event, {
    access: { deny: message => denied.push(message) },
    accessToken: { setCustomClaim: (...args) => claims.push(['access', ...args]) },
    refreshToken: refreshToken ?? { setMetadata: (key, value) => metadata[key] = value },
    idToken: { setCustomClaim: (...args) => claims.push(['id', ...args]) },
  });
  return { denied, claims, metadata };
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
    client: { client_id: 'other' } }), { denied: [], claims: [], metadata: {} });
});

test('refresh preserves original login, ignores newer password login, and rejects missing metadata', async () => {
  const event = valid();
  event.transaction.protocol = 'oauth2-refresh-token';
  delete event.request;
  event.refresh_token = { metadata: { freeagent_primary_auth_time: '1791806400' } };
  event.authentication.methods[0].timestamp = new Date().toISOString();
  const result = await run(event);
  assert.equal(result.denied.length, 0);
  assert.equal(result.claims[0][2], 1791806400);
  for (const metadata of [{}, { freeagent_primary_auth_time: true },
    { freeagent_primary_auth_time: String(Math.floor(Date.now()/1000) - 2592000) },
    { freeagent_primary_auth_time: String(Math.floor(Date.now()/1000) + 100) }]) {
    event.refresh_token.metadata = metadata;
    assert.equal((await run(event)).denied.length, 1);
  }
  event.client.client_id = 'web';
  assert.equal((await run(event)).denied.length, 1);
});


test('initial metadata is carried unchanged across successive renewals', async () => {
  let event = valid();
  let result = await run(event);
  assert.deepEqual(result.metadata, { freeagent_primary_auth_time: '1791806400' });
  for (let i = 0; i < 3; i++) {
    event = valid();
    event.transaction.protocol = 'oauth2-refresh-token';
    event.refresh_token = { metadata: result.metadata };
    delete event.authentication;
    delete event.request;
    result = await run(event);
    assert.equal(result.denied.length, 0);
    assert.equal(result.claims[0][2], 1791806400);
    assert.deepEqual(result.metadata, { freeagent_primary_auth_time: '1791806400' });
  }
});
test('metadata capability missing fails closed and expiry boundary is exact', async () => {
  assert.equal((await run(valid(), {})).denied.length, 1);
  const event = valid();
  event.transaction.protocol = 'oauth2-refresh-token';
  for (const [age, denied] of [[2591999, 0], [2592000, 1], [2592001, 1]]) {
    event.refresh_token = { metadata: { freeagent_primary_auth_time: String(Date.now()/1000 - age) } };
    assert.equal((await run(event)).denied.length, denied);
  }
});

test('controlled access denies unknown users and empty or malformed configuration on login and refresh', async () => {
  for (const protocol of ['oidc-basic-profile', 'oauth2-refresh-token']) {
    for (const allowed of [undefined, '[]', 'bad', '{}', '[42]', '["auth0|other"]']) {
      const event = valid(); event.transaction.protocol = protocol;
      event.secrets.TEST_SUBJECTS = allowed;
      const result = await run(event);
      assert.equal(result.denied.length, 1); assert.equal(result.claims.length, 0);
    }
  }
});
