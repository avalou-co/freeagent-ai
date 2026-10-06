"""FreeAgent API client: credentials file, 401 refresh, one-command OAuth login.

Credentials live in a mode-600 JSON file outside any repo (default
~/.config/freeagent/credentials.json, override with FREEAGENT_CREDENTIALS):

    {"client_id": ..., "client_secret": ..., "access_token": ..., "refresh_token": ...}

Never print these values.
"""
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE = "https://api.freeagent.com/v2/"
CREDS_PATH = os.path.expanduser(
    os.environ.get("FREEAGENT_CREDENTIALS", "~/.config/freeagent/credentials.json")
)
PORT = 8080
REDIRECT = f"http://localhost:{PORT}/callback"


def _load():
    with open(CREDS_PATH) as f:
        return json.load(f)


def _save(creds):
    os.makedirs(os.path.dirname(CREDS_PATH), mode=0o700, exist_ok=True)
    fd = os.open(CREDS_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, json.dumps(creds).encode())
    finally:
        os.close(fd)


def _token_request(creds, params):
    basic = base64.b64encode(f"{creds['client_id']}:{creds['client_secret']}".encode()).decode()
    req = urllib.request.Request(
        BASE + "token_endpoint",
        data=urllib.parse.urlencode(params).encode(),
        headers={"Authorization": "Basic " + basic, "Accept": "application/json"},
    )
    return json.load(urllib.request.urlopen(req))


def _refresh(creds):
    creds["access_token"] = _token_request(
        creds, {"grant_type": "refresh_token", "refresh_token": creds["refresh_token"]}
    )["access_token"]
    _save(creds)
    return creds


def call(method, path, body=None, _retry=True):
    """Call the API. `path` is relative to /v2/ (e.g. 'timeslips?from_date=...').

    Returns parsed JSON, or the status code for empty responses. Refreshes the
    access token once on a 401. Raises urllib.error.HTTPError otherwise.
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
        resp = urllib.request.urlopen(req)
        raw = resp.read()
        return json.loads(raw) if raw else resp.status
    except urllib.error.HTTPError as e:
        if e.code == 401 and _retry:
            _refresh(creds)
            return call(method, path, body, _retry=False)
        raise


def login(timeout=300):
    """Open the approve page, catch the redirect on localhost, store tokens, exit.

    Requires REDIRECT to be registered on the FreeAgent app. Returns True on success.
    """
    creds = _load()
    result = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" not in q:
                self.send_response(404)
                self.end_headers()
                return
            try:
                t = _token_request(
                    creds,
                    {"grant_type": "authorization_code", "code": q["code"][0], "redirect_uri": REDIRECT},
                )
                creds.update(access_token=t["access_token"], refresh_token=t["refresh_token"])
                _save(creds)
                result["ok"] = True
                msg = "Done. You can close this tab."
            except Exception as e:  # noqa: BLE001
                msg = f"Token exchange failed: {e}"
            self.send_response(200)
            self.end_headers()
            self.wfile.write(msg.encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    server.timeout = timeout
    url = BASE + "approve_app?" + urllib.parse.urlencode(
        {"response_type": "code", "client_id": creds["client_id"], "redirect_uri": REDIRECT}
    )
    webbrowser.open(url)
    print(f"Opened FreeAgent approval page. Log in and click Approve (waiting up to {timeout}s)...", flush=True)
    server.handle_request()
    server.server_close()
    return bool(result.get("ok"))
