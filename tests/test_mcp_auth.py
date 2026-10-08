import asyncio

import pytest

from freeagent_ai.mcp_auth import MIN_TOKEN_LENGTH, TOKEN_ENV, BearerAuth, load_token

TOKEN = "t" * MIN_TOKEN_LENGTH


def _request(app, headers, scope_type="http"):
    sent = []
    inner_calls = []

    async def inner(scope, receive, send):
        inner_calls.append(scope)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def send(msg):
        sent.append(msg)

    async def receive():
        return {"type": "http.request"}

    asyncio.run(BearerAuth(inner, TOKEN)({"type": scope_type, "headers": headers}, receive, send))
    return sent, inner_calls


def test_valid_token_reaches_app():
    sent, calls = _request(None, [(b"authorization", b"Bearer " + TOKEN.encode())])
    assert len(calls) == 1 and sent[0]["status"] == 200


def test_scheme_is_case_insensitive():
    _, calls = _request(None, [(b"authorization", b"bearer " + TOKEN.encode())])
    assert len(calls) == 1


@pytest.mark.parametrize(
    "headers",
    [
        [],
        [(b"authorization", b"Bearer wrong")],
        [(b"authorization", b"Bearer ")],
        [(b"authorization", TOKEN.encode())],
        [(b"authorization", b"Basic " + TOKEN.encode())],
        [(b"x-api-key", TOKEN.encode())],
    ],
)
def test_missing_or_invalid_auth_is_rejected_before_app(headers):
    sent, calls = _request(None, headers)
    assert calls == []
    assert sent[0]["status"] == 401
    assert (b"www-authenticate", b"Bearer") in sent[0]["headers"]
    assert TOKEN.encode() not in sent[1]["body"]


def test_websocket_without_auth_closed():
    sent, calls = _request(None, [], scope_type="websocket")
    assert calls == [] and sent[0]["type"] == "websocket.close"


def test_load_token_fails_closed():
    for bad in [{}, {TOKEN_ENV: ""}, {TOKEN_ENV: "short"}, {TOKEN_ENV: " " + TOKEN}]:
        with pytest.raises(ValueError):
            load_token(bad)
    assert load_token({TOKEN_ENV: TOKEN}) == TOKEN


def test_empty_token_rejected_at_construction():
    with pytest.raises(ValueError):
        BearerAuth(lambda *a: None, "")


def test_http_mode_refuses_to_start_without_token(monkeypatch):
    mcp_server = pytest.importorskip("freeagent_ai.mcp_server", reason="mcp extra not installed")
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    with pytest.raises(ValueError):
        mcp_server.run(http=True)


def test_http_app_end_to_end_requires_token():
    mcp_server = pytest.importorskip("freeagent_ai.mcp_server", reason="mcp extra not installed")
    testclient = pytest.importorskip("starlette.testclient", reason="needs httpx")
    app = BearerAuth(mcp_server.mcp.streamable_http_app(), TOKEN)
    with testclient.TestClient(app) as c:
        assert c.post("/mcp", json={}).status_code == 401
        assert c.post("/mcp", json={}, headers={"Authorization": "Bearer nope"}).status_code == 401
        assert c.post("/mcp", json={}, headers={"Authorization": f"Bearer {TOKEN}"}).status_code != 401
