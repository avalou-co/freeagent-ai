import base64
import http.client
import json
import secrets
import socket
import threading
import time
import urllib.error
from email.message import Message
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp.types import TextContent
from starlette.testclient import TestClient

from freeagent_ai import hosted_files, hosted_network
from freeagent_ai.hosted_accounts import AccessDenied, Accounts, MemoryStore, Principal, TokenCipher, key_for
from freeagent_ai.hosted_app import create_app
from freeagent_ai.hosted_auth import ORIGIN, PRIMARY_AUTH_CLAIM, Settings, Verifier
from freeagent_ai.hosted_client import HostedClient, principal_context
from freeagent_ai.hosted_deadline import Deadline, deadline_context, rpc_timeout
from freeagent_ai.public_package import build, package_files
from freeagent_ai.public_tools import REGISTRY, Dispatcher


@pytest.fixture
def accounts():
    cipher = TokenCipher({"1": base64.b64encode(secrets.token_bytes(32)).decode()}, "1")
    return Accounts(MemoryStore(), cipher, clock=lambda: 100)


def link(accounts, subject="alice", company="1", generation=0):
    accounts.replace(
        subject,
        f"https://api.freeagent.com/v2/company/{company}",
        "production",
        {"access_token": subject, "refresh_token": "old-refresh", "expires_at": time.time() + 3600},
        generation,
    )
    return Principal(subject, frozenset({"freeagent:read", "freeagent:write"}), 101)


def test_replace_invalidates_tokens_minted_during_linking_and_never_rebinds(accounts):
    alice = link(accounts)
    old_binding = accounts.bind(alice)
    # Fresh auth used to open the relink page occurs before the actual replacement commit.
    in_transition = Principal("alice", alice.scopes, 102)
    accounts.clock = lambda: 103
    accounts.replace("alice", "company-2", "production", {"access_token": "new"}, 1)
    for principal in [alice, in_transition]:
        with pytest.raises(AccessDenied):
            accounts.bind(principal)
    with pytest.raises(AccessDenied):
        accounts.credentials(old_binding)
    fresh = accounts.bind(Principal("alice", alice.scopes, 104))
    assert fresh.company == "company-2"
    assert accounts.credentials(fresh)["access_token"] == "new"


def test_refresh_cannot_resurrect_after_disconnect_or_replace(accounts):
    principal = link(accounts)
    binding = accounts.bind(principal)

    def exchange(tokens):
        accounts.disconnect("alice", 1)
        return {"access_token": "rotated", "refresh_token": "rotated"}

    with pytest.raises(AccessDenied):
        accounts.refresh(binding, exchange)
    record = accounts.store.get("account_links", key_for("alice"))
    assert record == {"generation": 2, "active": False, "revoked_before": 100}


def test_refresh_uses_envelope_acquired_with_lease(accounts):
    binding = accounts.bind(link(accounts))
    original = accounts.store.mutate
    triggered = False

    def concurrent_refresh(collection, key, change):
        nonlocal triggered
        if collection == "account_links" and not triggered:
            triggered = True
            original(
                collection,
                key,
                lambda old: {**old, "tokens": accounts.cipher.seal({"refresh_token": "latest"}, binding.aad)},
            )
        return original(collection, key, change)

    accounts.store.mutate = concurrent_refresh
    seen = []
    accounts.refresh(binding, lambda tokens: seen.append(tokens["refresh_token"]) or {"access_token": "ok"})
    assert seen == ["latest"]


def test_cipher_binding_and_old_key_rotation(accounts):
    binding = accounts.bind(link(accounts))
    record = accounts.check(binding)
    with pytest.raises(AccessDenied):
        accounts.cipher.open(record["tokens"], binding.aad + "another-company")
    keys = {
        "1": base64.b64encode(secrets.token_bytes(32)).decode(),
        "2": base64.b64encode(secrets.token_bytes(32)).decode(),
    }
    old, rotated = TokenCipher(keys, "1"), TokenCipher(keys, "2")
    assert rotated.open(old.seal({"refresh_token": "private"}, "binding"), "binding")["refresh_token"] == "private"


def test_callback_states_one_use_and_expiring(accounts):
    state = accounts.new_state("freeagent", {"subject": "alice"})
    assert accounts.take_state(state, "freeagent")["subject"] == "alice"
    with pytest.raises(AccessDenied):
        accounts.take_state(state, "freeagent")
    expired = accounts.new_state("freeagent", {}, ttl=1)
    accounts.clock = lambda: 102
    with pytest.raises(AccessDenied):
        accounts.take_state(expired, "freeagent")


def settings():
    return Settings(
        "https://example.auth0.com/",
        "mcp-client",
        "web-client",
        "test-only-web-secret",
        "fa-client",
        "test-only-fa-secret",
        {},
        "1",
    )


def test_jwt_signature_audience_scope_and_auth_time():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = Verifier(
        settings(), SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key()))
    )
    now = int(time.time())
    payload = {
        "iss": settings().issuer,
        "aud": ORIGIN + "/mcp",
        "sub": "alice",
        "iat": now,
        "exp": now + 3600,
        "azp": "mcp-client",
        "scope": "freeagent:read",
        PRIMARY_AUTH_CLAIM: now - 10,
    }

    def token(data):
        return jwt.encode(data, private, algorithm="RS256")

    assert verifier.principal(token(payload)).scopes == frozenset({"freeagent:read"})
    for change in [
        {"aud": "other"},
        {"exp": now - 1},
        {"azp": "other"},
        {PRIMARY_AUTH_CLAIM: True},
        {PRIMARY_AUTH_CLAIM: now + 100},
        {"exp": now + 7200},
    ]:
        with pytest.raises(AccessDenied):
            verifier.principal(token({**payload, **change}))
    without = dict(payload)
    without.pop(PRIMARY_AUTH_CLAIM)
    with pytest.raises(AccessDenied):
        verifier.principal(token(without))


def test_public_no_arbitrary_executor_and_file_schema():
    assert not {"freeagent_get", "freeagent_post", "freeagent_put", "freeagent_delete"} & REGISTRY.keys()
    for operation in REGISTRY.values():
        annotations = operation.descriptor.model_dump(by_alias=True)["annotations"]
        assert all(isinstance(annotations[key], bool) for key in ["readOnlyHint", "destructiveHint", "openWorldHint"])
        assert (
            not {"path", "method", "operation", "receipt_path", "attachment_path"}
            & operation.descriptor.input_schema["properties"].keys()
        )
    schema = REGISTRY["create_expense"].descriptor.input_schema["properties"]["receipt"]
    assert set(schema["properties"]) == {"download_url", "file_id", "file_name", "mime_type"}
    assert set(schema["required"]) == {"download_url", "file_id"}
    assert REGISTRY["create_expense"].descriptor.meta["openai/fileParams"] == ["receipt"]


def test_dispatch_scope_and_approval_precede_provider_call(accounts):
    principal = link(accounts)
    dispatcher = Dispatcher(accounts, "id", "secret", client_factory=lambda *_: pytest.fail("provider must not run"))
    p = principal_context.set(Principal("alice", frozenset({"freeagent:read"}), 101))
    d = deadline_context.set(Deadline())
    try:
        with pytest.raises(AccessDenied):
            dispatcher.invoke("delete_timeslip", {"id": "1", "confirmed": True})
        principal_context.set(principal)
        with pytest.raises(AccessDenied):
            dispatcher.invoke("delete_timeslip", {"id": "1", "confirmed": False})
    finally:
        principal_context.reset(p)
        deadline_context.reset(d)


def test_successful_create_failed_readback_preserves_resource(accounts):
    principal = link(accounts)
    calls = []

    def transport(method, url, deadline, **kwargs):
        calls.append(method)
        if method == "POST":
            return {"contact": {"url": "https://api.freeagent.com/v2/contacts/7"}}, {}
        raise TimeoutError()

    dispatcher = Dispatcher(
        accounts, "id", "secret", client_factory=lambda *args: HostedClient(*args, transport=transport)
    )
    p, d = principal_context.set(principal), deadline_context.set(Deadline())
    try:
        result = dispatcher.call_tool("create_contact", {"organisation_name": "Sample", "confirmed": True})
        assert result.is_error
        assert isinstance(result.content[0], TextContent)
        assert "contacts/7" in result.content[0].text
        assert "original company" in result.content[0].text
        assert calls == ["POST", "GET"]
    finally:
        principal_context.reset(p)
        deadline_context.reset(d)


def test_provider_validation_is_reported_without_retry_or_local_rules(accounts):
    principal = link(accounts)
    calls = []

    def reject(method, url, deadline, **kwargs):
        calls.append((method, kwargs["body"]))
        raise urllib.error.HTTPError(
            url, 422, "validation", Message(), BytesIO(b'{"errors":{"hours":"provider rejects value"}}')
        )

    dispatcher = Dispatcher(
        accounts, "id", "secret", client_factory=lambda *args: HostedClient(*args, transport=reject)
    )
    p, d = principal_context.set(principal), deadline_context.set(Deadline())
    try:
        result = dispatcher.call_tool(
            "create_timeslip",
            {"user": "1", "project": "2", "task": "3", "dated_on": "2026-01-01", "hours": "-10", "confirmed": True},
        )
        assert result.is_error
        assert isinstance(result.content[0], TextContent)
        assert "provider rejects value" in result.content[0].text
        assert len(calls) == 1
        assert calls[0][1]["timeslip"]["hours"] == "-10"
    finally:
        principal_context.reset(p)
        deadline_context.reset(d)


def test_pagination_rejects_cross_origin_and_deadline(accounts):
    binding = accounts.bind(link(accounts))
    calls = []

    def transport(method, url, deadline, **kwargs):
        calls.append(url)
        return {"contacts": []}, {"Link": '<https://example.invalid/contacts>; rel="next"'}

    client = HostedClient(accounts, binding, Deadline(), "id", "secret", transport)
    with pytest.raises(ValueError):
        client.call("GET", "contacts")
    assert len(calls) == 1
    expired = Deadline(-1)
    with pytest.raises(TimeoutError):
        expired.sleep(1)
    d = deadline_context.set(Deadline(0.5))
    try:
        assert 0 < rpc_timeout() <= 0.5
    finally:
        deadline_context.reset(d)


def test_mixed_private_dns_and_untrusted_download_never_connect(monkeypatch):
    resolver = SimpleNamespace(resolve=lambda *args, **kwargs: ["8.8.8.8", "169.254.169.254"])
    with pytest.raises(ValueError):
        hosted_network.resolve_public("files.example", Deadline(), resolver)
    monkeypatch.setattr(hosted_files, "resolve_public", lambda *_: pytest.fail("untrusted origin must not resolve"))
    for url in [
        "http://files.example/a",
        "https://files.example.evil/a",
        "https://user@files.example/a",
        "https://files.example:444/a",
    ]:
        with pytest.raises(ValueError):
            hosted_files.download({"download_url": url, "file_id": "file-1"}, frozenset({"files.example"}), Deadline())


def test_slow_drip_headers_cannot_extend_absolute_deadline():
    client, peer = socket.socketpair()
    client.settimeout(5)

    def drip():
        try:
            peer.sendall(b"HTTP/1.1 200 OK\r\nX-Slow: ")
            for _ in range(100):
                peer.sendall(b"x")
                time.sleep(0.01)
        except OSError:
            pass
        finally:
            peer.close()

    sender = threading.Thread(target=drip, daemon=True)
    sender.start()
    started = time.monotonic()
    try:
        with pytest.raises((TimeoutError, OSError)), hosted_network.socket_budget(client, Deadline(0.1)):
            response = http.client.HTTPResponse(client)
            response.begin()
        assert time.monotonic() - started < 1
    finally:
        client.close()
        sender.join(timeout=1)


def test_hosted_http_identity_context_and_discovery(accounts):
    alice, bob = link(accounts), link(accounts, "bob", "2")
    seen = []

    class Dispatch:
        def call_tool(self, name, arguments):
            from mcp.types import CallToolResult, TextContent

            seen.append((principal_context.get().subject, deadline_context.get().remaining() > 0))
            return CallToolResult(content=[TextContent(type="text", text="sample")])

    verifier = SimpleNamespace(principal=lambda value: {"alice": alice, "bob": bob}[value])
    app = create_app(settings(), accounts, verifier, Dispatch())
    with TestClient(app, base_url=ORIGIN) as client:
        unauthenticated = client.post("/mcp", json={})
        assert unauthenticated.status_code == 401
        assert "oauth-protected-resource/mcp" in unauthenticated.headers["www-authenticate"]
        assert "no-store" in unauthenticated.headers["cache-control"]
        assert client.get("/.well-known/oauth-protected-resource/mcp").json()["resource"] == ORIGIN + "/mcp"
        descriptors = client.post(
            "/mcp",
            headers={"Authorization": "Bearer alice", "Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ).json()["result"]["tools"]
        assert len(descriptors) == len(REGISTRY)
        assert all(tool["securitySchemes"] == tool["_meta"]["securitySchemes"] for tool in descriptors)
        for subject in ["alice", "bob"]:
            response = client.post(
                "/mcp",
                headers={"Authorization": "Bearer " + subject, "Accept": "application/json, text/event-stream"},
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "get_company", "arguments": {}},
                },
            )
            assert response.status_code == 200
    assert seen == [("alice", True), ("bob", True)]


def test_package_reproducible_and_release_gate(tmp_path):
    root = Path(__file__).resolve().parents[1]
    first, second = tmp_path / "a.zip", tmp_path / "b.zip"
    build(root, first, draft=True)
    build(root, second, draft=True)
    assert first.read_bytes() == second.read_bytes()
    files = package_files(root)
    assert json.loads(files["mcp.json"])["mcpServers"]["freeagent"]["url"] == ORIGIN + "/mcp"
    assert len([key for key in files if key.startswith("skills/")]) == 8
    with pytest.raises(ValueError):
        build(root, tmp_path / "release.zip")
    with pytest.raises(ValueError):
        package_files(root, {"interface": {"clientSecret": "must-not-be-packaged"}})
