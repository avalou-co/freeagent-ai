# Auth

## One-time setup

1. Create an app at dev.freeagent.com. Note its OAuth identifier (client ID) and secret.
2. Register `http://localhost:47821/callback` as an OAuth redirect URI on the app.
3. Create `~/.config/freeagent/credentials.json` (mode 600, directory 700), or set `FREEAGENT_CREDENTIALS`:
   ```json
   {"client_id": "...", "client_secret": "...", "access_token": "", "refresh_token": ""}
   ```
   `expires_at` (UTC ISO datetime of the access token's expiry) is added automatically.
4. Run `freeagent-ai login`.

## How it works

- `login` opens the approve page in the default browser and runs a one-shot listener on `localhost:47821`.
  The user logs in if prompted and clicks **Approve**; the listener exchanges the code, stores the tokens, and exits.
  No listener is left running.
- `call()` sends the access token (about 1 hour life) and, on a 401, refreshes once with the refresh token and retries.
- If the refresh also fails, run `login` again.

## Gotchas

- The client **secret is not a bearer token**. Using it as one returns "Access token not recognised".
- Postman's redirect URIs drop the `code` from the URL; use the localhost redirect.
- Non-interactive shells do not load `~/.zshrc`. Keep credentials in the file, not in env vars.
- Never print, log or paste credentials or tokens.
