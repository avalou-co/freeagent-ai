import json
import os
import stat
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from freeagent_ai import client

CREDS = {"client_id": "a", "client_secret": "b", "access_token": "c", "refresh_token": "d"}


def test_save_is_mode_600_and_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setattr(client, "CREDS_PATH", str(tmp_path / "sub" / "credentials.json"))
    client._save({"client_id": "a", "client_secret": "b", "access_token": "c", "refresh_token": "d"})
    assert stat.S_IMODE(os.stat(client.CREDS_PATH).st_mode) == 0o600
    assert json.loads(Path(client.CREDS_PATH).read_text())["client_id"] == "a"


def test_store_token_records_expiry(tmp_path, monkeypatch):
    monkeypatch.setattr(client, "CREDS_PATH", str(tmp_path / "credentials.json"))
    creds = {"client_id": "a", "client_secret": "b", "access_token": "", "refresh_token": "r"}
    client._store_token(creds, {"access_token": "new", "expires_in": 3600})
    saved = json.loads(Path(client.CREDS_PATH).read_text())
    assert saved["access_token"] == "new"
    assert saved["refresh_token"] == "r"
    assert client.token_expiry() is not None


def test_save_tightens_existing_permissive_file(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    path.write_text("{}")
    path.chmod(0o644)
    monkeypatch.setattr(client, "CREDS_PATH", str(path))
    client._save(CREDS)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert json.loads(path.read_text())["access_token"] == "c"


def test_save_does_not_write_through_symlink(tmp_path, monkeypatch):
    target = tmp_path / "victim.txt"
    target.write_text("untouched")
    link = tmp_path / "credentials.json"
    link.symlink_to(target)
    monkeypatch.setattr(client, "CREDS_PATH", str(link))
    client._save(CREDS)
    assert target.read_text() == "untouched"
    assert not link.is_symlink()
    assert stat.S_IMODE(os.stat(link).st_mode) == 0o600


def test_failed_save_keeps_previous_file_and_leaves_no_temp(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    monkeypatch.setattr(client, "CREDS_PATH", str(path))
    client._save(CREDS)

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(client.os, "replace", boom)
    with pytest.raises(OSError):
        client._save({**CREDS, "access_token": "new"})
    assert json.loads(path.read_text())["access_token"] == "c"
    assert [p.name for p in tmp_path.iterdir()] == ["credentials.json"]


class _Server:
    """Local HTTP server on 127.0.0.1 (dummy credentials only) that records Authorization headers."""

    def __init__(self, handler):
        self.seen = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                outer.seen.append((self.path, self.headers.get("Authorization")))
                handler(self)

            do_POST = do_GET

            def log_message(self, format, *args):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}/"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def servers(tmp_path, monkeypatch):
    made = []

    def make(handler):
        srv = _Server(handler)
        made.append(srv)
        return srv

    monkeypatch.setattr(client, "CREDS_PATH", str(tmp_path / "credentials.json"))
    client._save(CREDS)
    yield make
    for srv in made:
        srv.close()


def _redirect_to(location, code=302):
    def handler(h):
        h.send_response(code)
        h.send_header("Location", location)
        h.end_headers()

    return handler


@pytest.mark.parametrize("code", [301, 302, 307, 308])
def test_get_redirect_to_other_host_is_refused_without_forwarding_token(servers, monkeypatch, code):
    foreign = servers(lambda h: (h.send_response(200), h.end_headers()))
    api = servers(_redirect_to(foreign.url + "collect", code))
    monkeypatch.setattr(client, "BASE", api.url)
    with pytest.raises(urllib.error.HTTPError) as exc:
        client.call("GET", "users/me")
    assert exc.value.code == code
    assert foreign.seen == []
    assert str(exc.value) != "c" and "Bearer" not in str(exc.value)


def test_write_redirect_is_refused(servers, monkeypatch):
    foreign = servers(lambda h: (h.send_response(200), h.end_headers()))
    api = servers(_redirect_to(foreign.url, 307))
    monkeypatch.setattr(client, "BASE", api.url)
    with pytest.raises(urllib.error.HTTPError):
        client.call("POST", "timeslips", {"timeslip": {}})
    assert foreign.seen == []


def test_token_request_redirect_is_refused_without_forwarding_client_credentials(servers, monkeypatch):
    foreign = servers(lambda h: (h.send_response(200), h.end_headers()))
    api = servers(_redirect_to(foreign.url, 307))
    monkeypatch.setattr(client, "BASE", api.url)
    with pytest.raises(urllib.error.HTTPError):
        client._token_request(CREDS, {"grant_type": "refresh_token", "refresh_token": "d"})
    assert foreign.seen == []


def test_redirect_same_host_http_downgrade_style_is_refused_too(servers, monkeypatch):
    api = servers(_redirect_to("http://127.0.0.1:1/x"))
    monkeypatch.setattr(client, "BASE", api.url)
    with pytest.raises(urllib.error.HTTPError):
        client.call("GET", "users/me")


def test_non_redirect_request_still_works_with_bearer_token(servers, monkeypatch):
    def ok(h):
        body = b'{"user": {"url": "x"}}'
        h.send_response(200)
        h.send_header("Content-Length", str(len(body)))
        h.end_headers()
        h.wfile.write(body)

    api = servers(ok)
    monkeypatch.setattr(client, "BASE", api.url)
    assert client.call("GET", "users/me") == {"user": {"url": "x"}}
    assert api.seen == [("/users/me", "Bearer c")]


# --- OAuth login callback ---


@pytest.fixture
def login_env(tmp_path, monkeypatch):
    """Run login() in a thread with a mocked token exchange; yields helpers to hit the callback."""
    monkeypatch.setattr(client, "CREDS_PATH", str(tmp_path / "credentials.json"))
    client._save(CREDS)
    sock = HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = sock.server_port
    sock.server_close()
    monkeypatch.setattr(client, "PORT", port)
    monkeypatch.setattr(client, "REDIRECT", f"http://localhost:{port}/callback")
    opened = []
    monkeypatch.setattr(client.webbrowser, "open", opened.append)
    exchanges = []

    def fake_token(creds, params):
        exchanges.append(params)
        return {"access_token": "new", "refresh_token": "r2", "expires_in": 3600}

    monkeypatch.setattr(client, "_token_request", fake_token)
    out = {}

    def start(timeout=5):
        t = threading.Thread(target=lambda: out.update(ok=client.login(timeout=timeout)))
        t.start()
        for _ in range(200):
            if opened:
                break
            threading.Event().wait(0.02)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(opened[0]).query)
        return t, q["state"][0]

    def hit(path):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}") as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    return start, hit, exchanges, out


def test_login_success_with_matching_state(login_env):
    start, hit, exchanges, out = login_env
    t, state = start()
    assert len(state) >= 32
    assert hit(f"/callback?code=DUMMY&state={state}") == 200
    t.join(5)
    assert out["ok"] is True
    assert len(exchanges) == 1 and exchanges[0]["code"] == "DUMMY"
    assert json.loads(Path(client.CREDS_PATH).read_text())["access_token"] == "new"


def test_forged_callbacks_rejected_and_do_not_consume_attempt(login_env):
    start, hit, exchanges, out = login_env
    t, state = start()
    assert hit("/anything?code=DUMMY") == 400  # wrong path, no state
    assert hit("/callback?code=DUMMY") == 400  # missing state
    assert hit("/callback?code=DUMMY&state=wrong") == 400
    assert hit(f"/callback?state={state}") == 400  # missing code
    assert hit(f"/callback?code=A&code=B&state={state}") == 400  # duplicate code
    assert hit(f"/callback?code=A&state={state}&state={state}") == 400  # duplicate state
    assert exchanges == []
    assert hit(f"/callback?code=GOOD&state={state}") == 200  # real login still works
    t.join(5)
    assert out["ok"] is True
    assert [e["code"] for e in exchanges] == ["GOOD"]


def test_login_times_out_and_releases_port(login_env):
    start, hit, exchanges, out = login_env
    t, state = start(timeout=1)
    assert hit("/callback?code=X&state=bad") == 400
    t.join(5)
    assert out["ok"] is False
    assert exchanges == []
    with HTTPServer(("127.0.0.1", client.PORT), BaseHTTPRequestHandler):
        pass  # listener closed: port can be bound again


@pytest.fixture
def responses(monkeypatch):
    from email.message import Message
    from io import BytesIO

    queue, requests, sleeps = [], [], []

    class Response(BytesIO):
        status = 200

        def __init__(self, data, link):
            super().__init__(json.dumps(data).encode())
            self.headers = Message()
            if link:
                self.headers["Link"] = link

    def open_request(req):
        requests.append(req)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return Response(*item)

    monkeypatch.setattr(client, "_load", lambda: dict(CREDS))
    monkeypatch.setattr(client._opener, "open", open_request)
    monkeypatch.setattr(client.time, "sleep", sleeps.append)
    return queue, requests, sleeps


def test_paginate_preserves_filters_and_combines_pages(responses):
    queue, requests, _ = responses
    queue.extend(
        [
            ({"invoices": [{"id": 1}]}, '<?view=overdue&page=2>; rel="next", <invoices?page=1>; rel="prev"'),
            ({"invoices": [{"id": 2}]}, ""),
        ]
    )
    assert client.call("GET", "invoices?view=overdue") == {"invoices": [{"id": 1}, {"id": 2}]}
    assert requests[1].full_url == client.BASE + "invoices?view=overdue&page=2"


def test_single_page_opt_out(responses):
    queue, requests, _ = responses
    queue.append(({"timeslips": []}, '<timeslips?page=2>; rel="next"'))
    assert client.call("GET", "timeslips", paginate=False) == {"timeslips": []}
    assert len(requests) == 1


@pytest.mark.parametrize(
    "target", ["https://evil.example/v2/invoices", "http://api.freeagent.com/v2/invoices", "/token_endpoint"]
)
def test_unsafe_next_link_rejected(responses, target):
    queue, requests, _ = responses
    queue.append(({"invoices": []}, f'<{target}>; rel="next"'))
    with pytest.raises(ValueError, match="outside"):
        client.call("GET", "invoices")
    assert len(requests) == 1


def test_pagination_cycle_rejected(responses):
    queue, requests, _ = responses
    queue.append(({"invoices": []}, '<invoices>; rel="next"'))
    with pytest.raises(ValueError, match="cycle"):
        client.call("GET", "invoices")
    assert len(requests) == 1


def rate_limit(value=None):
    from email.message import Message

    headers = Message()
    if value is not None:
        headers["Retry-After"] = value
    return urllib.error.HTTPError(client.BASE + "invoices", 429, "limited", headers, None)


@pytest.mark.parametrize("header,delay", [("2", 2), ("60", 60), (None, 1), ("invalid", 1)])
def test_rate_limit_then_success(responses, header, delay):
    queue, requests, sleeps = responses
    queue.extend([rate_limit(header), ({"invoices": []}, "")])
    assert client.call("GET", "invoices") == {"invoices": []}
    assert sleeps == [delay]
    assert len(requests) == 2


def test_rate_limit_exhaustion(responses):
    queue, requests, sleeps = responses
    queue.extend([rate_limit()] * 4)
    with pytest.raises(urllib.error.HTTPError):
        client.call("GET", "invoices")
    assert sleeps == [1, 2, 4]
    assert len(requests) == 4


@pytest.mark.parametrize("method,header", [("POST", "1"), ("GET", "61")])
def test_write_or_long_delay_is_not_retried(responses, method, header):
    queue, requests, sleeps = responses
    queue.append(rate_limit(header))
    with pytest.raises(urllib.error.HTTPError):
        client.call(method, "invoices")
    assert len(requests) == 1
    assert sleeps == []


def test_retry_after_http_date():
    from email.utils import format_datetime

    future = client.datetime.datetime.now(client.datetime.timezone.utc) + client.datetime.timedelta(seconds=10)
    assert 8 <= client._retry_delay(format_datetime(future, usegmt=True), 0) <= 10


def test_rate_limit_on_later_page(responses):
    queue, _, sleeps = responses
    queue.extend(
        [
            ({"bank_transactions": [1]}, '<bank_transactions?page=2>; rel="next"'),
            rate_limit("0"),
            ({"bank_transactions": [2]}, ""),
        ]
    )
    assert client.call("GET", "bank_transactions") == {"bank_transactions": [1, 2]}
    assert sleeps == [0]


def test_refresh_on_later_page_uses_new_token(responses, monkeypatch):
    from email.message import Message

    queue, requests, _ = responses
    creds = dict(CREDS)
    monkeypatch.setattr(client, "_load", lambda: creds)

    def refresh(current):
        current["access_token"] = "new"
        return current

    monkeypatch.setattr(client, "_refresh", refresh)
    queue.extend(
        [
            ({"invoices": [1]}, '<invoices?page=2>; rel="next"'),
            urllib.error.HTTPError(client.BASE + "invoices?page=2", 401, "expired", Message(), None),
            ({"invoices": [2]}, ""),
        ]
    )
    assert client.call("GET", "invoices") == {"invoices": [1, 2]}
    assert [req.get_header("Authorization") for req in requests] == ["Bearer c", "Bearer c", "Bearer new"]


def test_inconsistent_page_raises_instead_of_returning_partial_results(responses):
    queue, _, _ = responses
    queue.extend([({"invoices": [1]}, '<invoices?page=2>; rel="next"'), ({"error": "bad response"}, "")])
    with pytest.raises(ValueError, match="Inconsistent"):
        client.call("GET", "invoices")
