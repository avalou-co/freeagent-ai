// Auth0 custom OAuth2 connection fetchUserProfile script. No upstream tokens in Auth0.
function fetchUserProfile(accessToken, context, callback) {
  request.get({
    url: "https://freeagent-ai.avalou.co/connect/profile",
    headers: { Authorization: "Bearer " + accessToken },
    timeout: 5000,
  }, (err, response, body) => {
    if (err || response.statusCode !== 200) return callback(new Error("FreeAgent connection failed"));
    try {
      const profile = JSON.parse(body);
      if (!/^[a-f0-9]{64}$/.test(profile.user_id) ||
          typeof profile.app_metadata?.freeagent_login_receipt !== "string") {
        return callback(new Error("Invalid FreeAgent connection profile"));
      }
      callback(null, profile);
    } catch (_) {
      callback(new Error("Invalid FreeAgent connection profile"));
    }
  });
}
