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
from email.message import Message
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
from typing import Any

import httpx2
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential

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


def _retry_after(headers):
    """Read the server's delay; Tenacity supplies backoff when it is absent or invalid."""
    value = headers.get("Retry-After")
    if value is None:
        return None
    if value.isascii() and value.isdecimal():
        return int(value)
    try:
        date = parsedate_to_datetime(value)
        return max(0, (date - datetime.datetime.now(datetime.timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def _retryable(error):
    if not isinstance(error, urllib.error.HTTPError) or error.code != 429:
        return False
    delay = _retry_after(error.headers)
    return delay is None or delay <= 60


def _wait(retry_state):
    error = retry_state.outcome.exception()
    delay = _retry_after(error.headers)
    return delay if delay is not None else wait_exponential(multiplier=1, max=60)(retry_state)


def _error_headers(headers):
    result = Message()
    for name, value in headers.items():
        result[name] = value
    return result


def _request(method, path, body, refresh=True):
    creds = _load()
    with httpx2.Client(follow_redirects=False, timeout=60) as session:

        def send():
            nonlocal refresh
            resp = session.request(
                method,
                BASE + path,
                json=body,
                headers={"Authorization": "Bearer " + creds["access_token"], "Accept": "application/json"},
            )
            try:
                if resp.status_code == 401 and refresh:
                    resp.close()
                    _refresh(creds)
                    refresh = False
                    return send()
                if resp.status_code >= 300:
                    # Preserve the public client's existing HTTPError contract.
                    raise urllib.error.HTTPError(
                        str(resp.url),
                        resp.status_code,
                        resp.reason_phrase,
                        _error_headers(resp.headers),
                        BytesIO(resp.content),
                    )
                return (resp.json() if resp.content else resp.status_code), resp.links
            finally:
                resp.close()

        retries = Retrying(
            retry=retry_if_exception(lambda error: method == "GET" and _retryable(error)),
            stop=stop_after_attempt(4),
            wait=_wait,
            reraise=True,
            sleep=time.sleep,
        )
        return retries(send)


def _next_path(links, current):
    target = links.get("next", {}).get("url")
    if target is None:
        return None
    url = urllib.parse.urljoin(BASE + current, target)
    base, parsed = urllib.parse.urlsplit(BASE), urllib.parse.urlsplit(url)
    if (
        parsed.scheme != base.scheme
        or parsed.netloc != base.netloc
        or not parsed.path.startswith(base.path)
        or parsed.fragment
        or ".." in urllib.parse.unquote(parsed.path).split("/")
    ):
        raise ValueError("Pagination link is outside the FreeAgent API")
    return url[len(BASE) :]


def call(method, path, body=None, _retry=True, *, paginate=True) -> Any:
    """Call a /v2/-relative API path, returning JSON or an empty response's status.

    GETs aggregate list fields across Link rel=next pages by default. Set paginate=False
    for one page. GET 429s retry at most three times with waits of at most 60 seconds;
    writes are never retried on 429. Refreshes once per page on 401; refuses redirects.
    """
    method = method.upper()
    result, link = _request(method, path, body, _retry)
    if method != "GET" or not paginate:
        return result
    seen = {path}
    while next_path := _next_path(link, path):
        if next_path in seen or len(seen) >= 1000:
            raise ValueError("Pagination cycle or page limit exceeded")
        seen.add(next_path)
        page, link = _request(method, next_path, body, _retry)
        if not isinstance(result, dict) or not isinstance(page, dict):
            raise ValueError("Expected object responses for pagination")
        lists = [key for key, value in result.items() if isinstance(value, list)]
        if not lists or any(not isinstance(page.get(key), list) for key in lists):
            raise ValueError("Inconsistent pagination response")
        for key in lists:
            result[key].extend(page[key])
        path = next_path
    return result


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
