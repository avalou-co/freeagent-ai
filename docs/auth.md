# Auth

## Setup

1. Create an app at dev.freeagent.com and note its client ID and secret.
2. Add `http://localhost:47821/callback` as a redirect URI on the app.
3. Create a private credentials file (or point `FREEAGENT_CREDENTIALS` at another path):
   ```sh
   mkdir -p -m 700 ~/.config/freeagent
   install -m 600 /dev/null ~/.config/freeagent/credentials.json
   ```
   and put this in it:
   ```json
   {"client_id": "...", "client_secret": "...", "access_token": "", "refresh_token": ""}
   ```
   The tool adds `expires_at` (the token's UTC expiry) itself.
4. Run `freeagent-ai login`.

`Saving.` The tool writes a temp file and renames it over the old one, so a failed write keeps the previous file. The result is always mode 600, and a symlink at the path gets replaced rather than followed. A directory the tool creates is mode 700. It leaves an existing directory's permissions as they are, so check other users cannot read it.

## How login works

`login` opens the FreeAgent approve page in your browser and listens on `localhost:47821`. You log in if asked and click **Approve**. The listener swaps the code for tokens, saves them and exits.

Each login uses a random one-time `state`. The listener only accepts `/callback` with that state and one `code`. It answers anything else with a 400 and keeps waiting, for up to 300 seconds.

API and token requests do not follow redirects, so tokens cannot leak to another host or over plain HTTP. A redirect raises `HTTPError`.

`call()` sends the access token, which lasts about an hour. On a 401 it refreshes once and retries. If the refresh fails too, run `login` again.

## Gotchas

- The client secret is not an access token. Sending it as one returns "Access token not recognised".
- Postman's redirect URIs drop the `code`, so use the localhost one.
- Non-interactive shells do not load `~/.zshrc`. Keep credentials in the file, not in env vars.
