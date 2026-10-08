"""FreeAgent API client: credentials file, 401 refresh, one-command OAuth login.

Credentials live in a mode-600 JSON file outside any repo (default
~/.config/freeagent/credentials.json, override with FREEAGENT_CREDENTIALS):

    {"client_id": ..., "client_secret": ..., "access_token": ..., "refresh_token": ...}

Never print these values.
"""

import base64
import contextlib
import datetime
import hmac
import json
import os
import secrets
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE = "https://api.freeagent.com/v2/"
CREDS_PATH = os.path.expanduser(os.environ.get("FREEAGENT_CREDENTIALS", "~/.config/freeagent/credentials.json"))
PORT = 47821
REDIRECT = f"http://localhost:{PORT}/callback"


def _load():
    with open(CREDS_PATH) as f:
        return json.load(f)


def _save(creds):
    """Write credentials atomically with mode 0600, never following a symlink at the target.

    The data goes to a fresh private temp file in the same directory, is flushed to disk, then
    renamed over the target. A failure leaves the previous file untouched and removes the temp file.
    If the target is a symlink, the link is replaced and its destination is not written.
    """
    directory = os.path.dirname(CREDS_PATH) or "."
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".credentials-", suffix=".tmp")  # created 0600
    try:
        with os.fdopen(fd, "wb") as f:
            os.fchmod(f.fileno(), 0o600)
            f.write(json.dumps(creds).encode())
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, CREDS_PATH)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect so bearer tokens and client credentials never leave the API origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, f"redirect refused (HTTP {code})", headers, fp)


_opener = urllib.request.build_opener(_NoRedirect)


def _token_request(creds, params):
    basic = base64.b64encode(f"{creds['client_id']}:{creds['client_secret']}".encode()).decode()
    req = urllib.request.Request(
        BASE + "token_endpoint",
        data=urllib.parse.urlencode(params).encode(),
        headers={"Authorization": "Basic " + basic, "Accept": "application/json"},
    )
    return json.load(_opener.open(req))


def _store_token(creds, t):
    creds["access_token"] = t["access_token"]
    if "refresh_token" in t:
        creds["refresh_token"] = t["refresh_token"]
    expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=int(t["expires_in"]))
    creds["expires_at"] = expires.isoformat(timespec="seconds")
    _save(creds)


def _refresh(creds):
    _store_token(creds, _token_request(creds, {"grant_type": "refresh_token", "refresh_token": creds["refresh_token"]}))
    return creds


def token_expiry():
    """Access token expiry as an aware UTC datetime, or None if unknown."""
    exp = _load().get("expires_at")
    return datetime.datetime.fromisoformat(exp) if exp else None


def call(method, path, body=None, _retry=True):
    """Call the API. `path` is relative to /v2/ (e.g. 'timeslips?from_date=...').

    Returns parsed JSON, or the status code for empty responses. Refreshes the
    access token once on a 401. Raises urllib.error.HTTPError otherwise,
    including for any redirect (never followed, so credentials stay on the API origin).
    """
    creds = _load()
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={
            "Authorization": "Bearer " + creds["access_token"],
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        resp = _opener.open(req)
        raw = resp.read()
        return json.loads(raw) if raw else resp.status
    except urllib.error.HTTPError as e:
        if e.code == 401 and _retry:
            _refresh(creds)
            return call(method, path, body, _retry=False)
        raise


def login(timeout=300):
    """Open the approve page, catch the redirect on localhost, store tokens, exit.

    Requires REDIRECT to be registered on the FreeAgent app. A random one-use `state` binds the
    callback to this login; requests with another path, a missing/wrong/repeated state or code are
    rejected without ending the attempt. Gives up after `timeout` seconds overall.
    Returns True on success.
    """
    creds = _load()
    state = secrets.token_urlsafe(32)
    result = {}

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status, msg):
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(msg.encode())

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(parsed.query)
            got_state = q.get("state", [])
            codes = q.get("code", [])
            valid = (
                parsed.path == "/callback"
                and not result
                and len(got_state) == 1
                and len(codes) == 1
                and hmac.compare_digest(got_state[0].encode(), state.encode())
            )
            if not valid:
                self._reply(400, "Invalid callback.")
                return
            result["used"] = True  # one use: a repeat of this callback is rejected
            try:
                t = _token_request(
                    creds,
                    {"grant_type": "authorization_code", "code": codes[0], "redirect_uri": REDIRECT},
                )
                _store_token(creds, t)
                result["ok"] = True
                self._reply(200, "Done. You can close this tab.")
            except Exception:  # noqa: BLE001
                self._reply(500, "Token exchange failed. Run the login again.")

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    try:
        url = (
            BASE
            + "approve_app?"
            + urllib.parse.urlencode(
                {"response_type": "code", "client_id": creds["client_id"], "redirect_uri": REDIRECT, "state": state}
            )
        )
        webbrowser.open(url)
        print(f"Opened FreeAgent approval page. Log in and click Approve (waiting up to {timeout}s)...", flush=True)
        deadline = time.monotonic() + timeout
        while not result.get("used"):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            server.timeout = remaining
            server.handle_request()
    finally:
        server.server_close()
    return bool(result.get("ok"))
