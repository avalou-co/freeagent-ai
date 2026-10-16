// Deploy through avalou-infrastructure. Refresh-token metadata must be enabled.
const MAX_SESSION_SECONDS = 30 * 24 * 60 * 60;
const METADATA_KEY = "freeagent_primary_auth_time";
exports.onExecutePostLogin = async (event, api) => {
  const mcp = event.client.client_id === event.secrets.MCP_CLIENT_ID;
  if (!mcp && event.client.client_id !== event.secrets.WEB_CLIENT_ID) return;
  let subjects;
  try { subjects = JSON.parse(event.secrets.TEST_SUBJECTS || "[]"); } catch { subjects = []; }
  if (!Array.isArray(subjects) || !subjects.every(s => typeof s === "string" && s.length > 0) ||
      !subjects.includes(event.user?.user_id)) {
    api.access.deny("This account is not approved for controlled testing.");
    return;
  }
  const refresh = event.transaction?.protocol === "oauth2-refresh-token";
  const query = event.request?.query;
  if (event.connection?.strategy !== "auth0" || (refresh && !mcp)) {
    api.access.deny("Use the dedicated database login.");
    return;
  }
  let timestamp;
  if (refresh) {
    // Never use current time, user metadata, or a new login to renew an old family.
    const stored = event.refresh_token?.metadata?.[METADATA_KEY];
    timestamp = typeof stored === "string" && /^[0-9]+$/.test(stored) ? Number(stored) : NaN;
  } else {
    if (event.transaction?.protocol !== "oidc-basic-profile" ||
        typeof query?.code_challenge !== "string" ||
        !/^[A-Za-z0-9_-]{43}$/.test(query.code_challenge) ||
        query.code_challenge_method !== "S256") {
      api.access.deny("Authorization code with PKCE S256 is required.");
      return;
    }
    const methods = (event.authentication?.methods || []).filter(method => method.name === "pwd");
    timestamp = methods.length === 1 ? Date.parse(methods[0].timestamp) / 1000 : NaN;
    timestamp = Math.floor(timestamp);
  }
  const now = Date.now() / 1000;
  if (!Number.isSafeInteger(timestamp) || timestamp <= 0 || timestamp > now ||
      (mcp && now >= timestamp + MAX_SESSION_SECONDS)) {
    api.access.deny("Primary authentication expired or unavailable; sign in again.");
    return;
  }
  if (mcp) {
    // Auth0 carries this server-owned metadata through the rotating token family.
    // Missing capability fails closed rather than issuing a renewable unbound session.
    if (typeof api.refreshToken?.setMetadata !== "function") {
      api.access.deny("Refresh-token metadata is unavailable; contact the operator.");
      return;
    }
    api.refreshToken.setMetadata(METADATA_KEY, String(timestamp));
  }
  const claim = "https://freeagent-ai.avalou.co/primary_auth_time";
  api.accessToken.setCustomClaim(claim, timestamp);
  api.idToken.setCustomClaim(claim, timestamp);
};
