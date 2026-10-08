# Auth

## One-time setup

1. Create an app at dev.freeagent.com. Note its OAuth identifier (client ID) and secret.
2. Register `http://localhost:47821/callback` as an OAuth redirect URI on the app.
3. Create the credentials file with a private directory and file, or set `FREEAGENT_CREDENTIALS`:
   ```sh
   mkdir -p -m 700 ~/.config/freeagent
   install -m 600 /dev/null ~/.config/freeagent/credentials.json
   ```
   then put this in it (`~/.config/freeagent/credentials.json`):
   ```json
   {"client_id": "...", "client_secret": "...", "access_token": "", "refresh_token": ""}
   ```
   `expires_at` (UTC ISO datetime of the access token's expiry) is added automatically.
4. Run `freeagent-ai login`.

Saving credentials is atomic and always results in mode 600, even over an existing file with looser permissions. A temp file in the same directory is renamed over the target, so a failed write keeps the previous file, and a symlink at the path is replaced rather than written through. A directory the tool creates is mode 700; one that already exists keeps its permissions, so make sure it is not accessible to other users.

## How it works

- `login` opens the approve page in the default browser and runs a one-shot listener on `localhost:47821`.
  The user logs in if prompted and clicks **Approve**; the listener exchanges the code, stores the tokens, and exits.
  Each login carries a random one-use `state`; only `/callback` with the matching state and a single `code` is accepted. Anything else gets a 400 and the login keeps waiting until the overall deadline (300s). No listener is left running.
- API and token requests never follow redirects, so tokens and client credentials cannot be forwarded to another host or over plain HTTP. A redirect surfaces as an `HTTPError`.
- `call()` sends the access token (about 1 hour life) and, on a 401, refreshes once with the refresh token and retries.
- If the refresh also fails, run `login` again.

## Gotchas

- The client **secret is not a bearer token**. Using it as one returns "Access token not recognised".
- Postman's redirect URIs drop the `code` from the URL; use the localhost redirect.
- Non-interactive shells do not load `~/.zshrc`. Keep credentials in the file, not in env vars.
- Never print, log or paste credentials or tokens.
