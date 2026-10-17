// Deploy through the operator's Terraform configuration. Refresh-token metadata must be enabled.
const MAX_SESSION_SECONDS = 30 * 24 * 60 * 60;
const METADATA_KEY = "freeagent_primary_auth_time";
exports.onExecutePostLogin = async (event, api) => {
  const mcp = event.client.client_id === event.secrets.MCP_CLIENT_ID;
  if (!mcp && event.client.client_id !== event.secrets.WEB_CLIENT_ID) return;
  const refresh = event.transaction?.protocol === "oauth2-refresh-token";
  const query = event.request?.query;
  if ((event.connection?.strategy !== "auth0" && event.connection?.strategy !== "oauth2") || (refresh && !mcp) ||
      (event.secrets.FREEAGENT_CONNECTION_SECRET && event.connection?.strategy === "auth0")) {
    api.access.deny("Use the dedicated database login.");
    return;
  }
  let timestamp, generation;
  const federated = event.connection?.strategy === "oauth2" && event.connection?.name === "freeagent";
  if (refresh) {
    // Never use current time, user metadata, or a new login to renew an old family.
    const stored = event.refresh_token?.metadata?.[METADATA_KEY];
    timestamp = typeof stored === "string" && /^[0-9]+$/.test(stored) ? Number(stored) : NaN;
    if (federated) {
      const saved = event.refresh_token?.metadata?.freeagent_connection_generation;
      generation = typeof saved === "string" && /^[1-9][0-9]*$/.test(saved) ? Number(saved) : NaN;
    }
  } else {
    if (event.transaction?.protocol !== "oidc-basic-profile" ||
        typeof query?.code_challenge !== "string" ||
        !/^[A-Za-z0-9_-]{43}$/.test(query.code_challenge) ||
        query.code_challenge_method !== "S256") {
      api.access.deny("Authorization code with PKCE S256 is required.");
      return;
    }
    if (federated && event.secrets.FREEAGENT_CONNECTION_SECRET) {
      // A single-use receipt binds this upstream login to the exact Auth0 subject.
      // A cached SSO profile cannot revive a disconnected generation.
      try {
        const response = await fetch("https://freeagent-ai.avalou.co/connect/complete", {
          method: "POST",
          headers: { "Authorization": "Basic " + Buffer.from(
            "freeagent-ai-auth0:" + event.secrets.FREEAGENT_CONNECTION_SECRET).toString("base64"),
            "Content-Type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams({ subject: event.user.user_id,
            receipt: event.user.app_metadata?.freeagent_login_receipt || "" }),
          signal: AbortSignal.timeout(5000),
        });
        if (!response.ok) throw new Error("Connection rejected");
        const login = await response.json();
        timestamp = login.authenticated_at;
        generation = login.generation;
      } catch (_) {
        api.access.deny("Connect again through FreeAgent; the login could not be completed.");
        return;
      }
    } else {
      const methods = (event.authentication?.methods || []).filter(method => method.name === "pwd");
      timestamp = methods.length === 1 ? Date.parse(methods[0].timestamp) / 1000 : NaN;
      timestamp = Math.floor(timestamp);
    }
  }
  const now = Date.now() / 1000;
  if ((federated && (!Number.isSafeInteger(generation) || generation < 1)) ||
      (event.connection?.strategy === "oauth2" && !federated) ||
      !Number.isSafeInteger(timestamp) || timestamp <= 0 || timestamp > now ||
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
    if (federated) api.refreshToken.setMetadata("freeagent_connection_generation", String(generation));
  }
  const claim = "https://freeagent-ai.avalou.co/primary_auth_time";
  api.accessToken.setCustomClaim(claim, timestamp);
  api.idToken.setCustomClaim(claim, timestamp);
  if (federated) {
    api.accessToken.setCustomClaim("https://freeagent-ai.avalou.co/connection_generation", generation);
    api.idToken.setCustomClaim("https://freeagent-ai.avalou.co/connection_generation", generation);
  }
};
