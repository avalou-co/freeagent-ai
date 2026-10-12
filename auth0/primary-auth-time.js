// Deploy this reviewed Post Login Action to the dedicated Auth0 database tenant.
// Set secrets MCP_CLIENT_ID and WEB_CLIENT_ID (public IDs, managed as Action secrets).
exports.onExecutePostLogin = async (event, api) => {
  const clients = [event.secrets.MCP_CLIENT_ID, event.secrets.WEB_CLIENT_ID];
  if (!clients.includes(event.client.client_id)) return;
  const query = event.request?.query;
  if (event.transaction?.protocol !== "oidc-basic-profile" ||
      typeof query?.code_challenge !== "string" ||
      !/^[A-Za-z0-9_-]{43}$/.test(query.code_challenge) ||
      query.code_challenge_method !== "S256") {
    api.access.deny("Authorization code with PKCE S256 is required.");
    return;
  }
  if (event.transaction.protocol === "oauth2-refresh-token" ||
      event.connection.strategy !== "auth0") {
    api.access.deny("Use a fresh database login; refresh grants are disabled.");
    return;
  }
  const methods = (event.authentication?.methods || []).filter(method => method.name === "pwd");
  if (methods.length !== 1) {
    api.access.deny("Primary authentication timestamp unavailable; sign in again.");
    return;
  }
  const timestamp = Date.parse(methods[0].timestamp) / 1000;
  if (!Number.isFinite(timestamp) || timestamp <= 0) {
    api.access.deny("Invalid authentication timestamp.");
    return;
  }
  const claim = "https://freeagent-ai.avalou.co/primary_auth_time";
  api.accessToken.setCustomClaim(claim, timestamp);
  api.idToken.setCustomClaim(claim, timestamp);
};
