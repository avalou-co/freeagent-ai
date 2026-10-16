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


def test_jwt_signature_audience_scope_and_auth_time(monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = Verifier(
        settings(), SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key()))
    )
    now = int(time.time())
    monkeypatch.setattr("freeagent_ai.hosted_auth.time.time", lambda: now)
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
    assert verifier.principal(token({**payload, PRIMARY_AUTH_CLAIM: now - 30 * 86400 + 1}))
    for change in [
        {"aud": "other"},
        {"exp": now - 1},
        {"azp": "other"},
        {PRIMARY_AUTH_CLAIM: True},
        {PRIMARY_AUTH_CLAIM: now + 100},
        {"exp": now + 7200},
        {PRIMARY_AUTH_CLAIM: now - 30 * 86400},
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
    expected_skills = {f"skills/{path.parent.name}/SKILL.md" for path in (root / ".agents/skills").glob("*/SKILL.md")}
    assert {key for key in files if key.startswith("skills/")} == expected_skills
    with pytest.raises(ValueError):
        build(root, tmp_path / "release.zip")
    with pytest.raises(ValueError):
        package_files(root, {"interface": {"clientSecret": "must-not-be-packaged"}})


def test_renewed_jwt_cannot_restore_disconnected_or_replaced_account(accounts):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = Verifier(
        settings(), SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key()))
    )
    now = int(time.time())
    accounts.clock = lambda: now - 86400 - 1
    link(accounts)
    payload = {
        "iss": settings().issuer,
        "aud": ORIGIN + "/mcp",
        "sub": "alice",
        "iat": now,
        "exp": now + 3600,
        "azp": "mcp-client",
        "scope": "freeagent:read",
        PRIMARY_AUTH_CLAIM: now - 86400,
    }
    renewed = verifier.principal(jwt.encode(payload, private, algorithm="RS256"))
    assert accounts.bind(renewed).subject == "alice"
    accounts.clock = lambda: now
    accounts.disconnect("alice", 1)
    with pytest.raises(AccessDenied):
        accounts.bind(renewed)
    accounts.replace("alice", "company-2", "production", {"access_token": "new"}, 2)
    with pytest.raises(AccessDenied):
        accounts.bind(renewed)
    # A genuinely new primary login can bind only the replacement company.
    accounts.clock = lambda: now + 2
    assert accounts.bind(Principal("alice", renewed.scopes, now + 1)).company == "company-2"


@pytest.fixture
def landing_config():
    return {
        "listing_url": "https://chatgpt.com/apps/test-only-listing",
        "privacy_url": "https://publisher.example/privacy",
        "terms_url": "https://publisher.example/terms",
        "support_url": "https://publisher.example/support",
        "policies_approved": True,
    }


def test_landing_launch_gate_and_backend_routes(accounts, monkeypatch, landing_config):
    monkeypatch.setenv("FREEAGENT_LANDING_CONFIG", json.dumps(landing_config))
    verifier = SimpleNamespace(principal=lambda _: (_ for _ in ()).throw(AccessDenied("invalid")))
    app = create_app(settings(), accounts, verifier)
    with TestClient(app, base_url=ORIGIN) as client:
        response = client.get("/")
        assert "Connect in ChatGPT" in response.text
        assert "Claude, connection unavailable" in response.text
        assert landing_config["listing_url"] in response.text
        assert "style-src 'self'" in response.headers["content-security-policy"]
        for path in [
            "/",
            "/account",
            "/login",
            "/auth/callback",
            "/freeagent/callback",
            "/.well-known/oauth-protected-resource/mcp",
            "/.well-known/oauth-protected-resource",
            "/.well-known/openai-apps-challenge",
            "/health",
            "/mcp",
        ]:
            response = client.get(path, follow_redirects=False)
            assert response.headers["cache-control"] == "no-store"
            assert response.status_code != 405
            if path not in ("/",):
                assert "style-src" not in response.headers["content-security-policy"]
                assert "Connect your assistant." not in response.text
        for path in ["/link", "/disconnect"]:
            response = client.post(path, follow_redirects=False)
            assert response.status_code == 400
            assert response.headers["cache-control"] == "no-store"
        for path in ["/privacy", "/terms", "/support"]:
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 302
            assert response.headers["location"] == landing_config[path[1:] + "_url"]
        response = client.get("/landing-assets/site.css")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/css")
        assert client.get("/landing-assets/fonts/hanken-grotesk-latin.woff2").status_code == 200
        assert client.get("/landing-assets/missing.css").status_code == 404
        assert client.get("/landing-assets/../hosted_auth.py").status_code == 404
        response = client.post("/mcp")
        assert response.status_code == 401
        assert "resource_metadata=" in response.headers["www-authenticate"]


def test_landing_disabled_until_launch(accounts, monkeypatch):
    monkeypatch.delenv("FREEAGENT_LANDING_CONFIG", raising=False)
    with TestClient(create_app(settings(), accounts, SimpleNamespace()), base_url=ORIGIN) as client:
        assert "Connect your assistant." not in client.get("/").text
        privacy = client.get("/privacy")
        assert privacy.status_code == 200
        assert "connected FreeAgent AI service" in privacy.text
        assert "encrypted FreeAgent access and refresh tokens" in privacy.text
        assert "no automatic expiry" in privacy.text
        assert "Review proposed accounting changes" in client.get("/terms").text
        assert "hello@avalou.co" in client.get("/support").text


@pytest.mark.parametrize(
    "change",
    [
        {"policies_approved": False},
        {"policies_approved": "true"},
        {"support_url": ""},
        {"listing_url": "https://chatgpt.com/"},
        {"listing_url": "https://chatgpt.com.evil.example/apps/test"},
        {"listing_url": "javascript:alert(1)"},
        {"claude_url": "https://claude.ai.evil.example/connectors/test"},
        {"claude_url": "javascript:alert(1)"},
        {"privacy_url": "http://publisher.example/privacy"},
        {"privacy_url": "https://freeagent-ai.avalou.co/account"},
        {"terms_url": "https://user:pass@publisher.example/terms"},
        {"terms_url": "https://publisher.example:8443/terms"},
        {"support_url": "https://publisher.example/\nheader"},
    ],
)
def test_landing_refuses_incomplete_or_unsafe_launch(accounts, monkeypatch, landing_config, change):
    monkeypatch.setenv("FREEAGENT_LANDING_CONFIG", json.dumps({**landing_config, **change}))
    with pytest.raises(ValueError):
        create_app(settings(), accounts, SimpleNamespace())


def test_landing_static_export_and_escaping(tmp_path, landing_config):
    from freeagent_ai.landing import build, load_config

    landing_config["listing_url"] += '?value="quoted"&second=two'
    config = tmp_path / "launch.json"
    config.write_text(json.dumps(landing_config))
    output = tmp_path / "static"
    build(output, load_config(config))
    document = (output / "index.html").read_text()
    assert "?value=&quot;quoted&quot;&amp;second=two" in document
    assert "{{" not in document
    assert (output / "landing-assets/fonts/libre-caslon-text-latin-regular.woff2").is_file()
    assert (output / "landing-assets/site.js").is_file()


@pytest.mark.parametrize("enabled", [(), ("listing_url",), ("claude_url",), ("listing_url", "claude_url")])
def test_provider_availability_is_independent(landing_config, enabled):
    from html.parser import HTMLParser

    from freeagent_ai.landing import render, validate_config

    class Controls(HTMLParser):
        def __init__(self):
            super().__init__()
            self.providers = []

        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if "provider-button" in (values.get("class") or "").split():
                self.providers.append((tag, values))

    config = {key: value for key, value in landing_config.items() if key != "listing_url"}
    urls = {"listing_url": landing_config["listing_url"], "claude_url": "https://claude.ai/connectors/test-only"}
    config.update({key: urls[key] for key in enabled})
    parser = Controls()
    parser.feed(render(validate_config(config)))
    assert len(parser.providers) == 2
    for tag, attrs in parser.providers:
        key = "listing_url" if "provider-chatgpt" in attrs["class"] else "claude_url"
        if key in enabled:
            assert tag == "a"
            assert attrs["href"] == urls[key]
        else:
            assert tag == "button"
            assert "disabled" in attrs
            assert "href" not in attrs
            assert "connection unavailable" in attrs["aria-label"]


def test_static_export_keeps_connections_unavailable(tmp_path):
    from freeagent_ai.landing import build_static

    build_static(tmp_path)
    index = (tmp_path / "index.html").read_text()
    assert index.count('type="button" disabled') == 2
    assert 'href="/account"' not in index
    assert "{{" not in index
    for slug in ("index.html", "privacy/index.html", "terms/index.html", "support/index.html"):
        content = (tmp_path / slug).read_text().lower()
        assert "pre-launch" not in content
        assert "coming soon" not in content
    for slug in ("privacy", "terms", "support"):
        assert f'href="/{slug}/"' in index
        assert "hello@avalou.co" in (tmp_path / slug / "index.html").read_text()
    privacy = (tmp_path / "privacy/index.html").read_text()
    assert "connected FreeAgent AI service" in privacy
    assert "encrypted FreeAgent access and refresh tokens" in privacy
    assert "no automatic expiry" in privacy
    assert not (tmp_path / "account").exists()
    assert not (tmp_path / "mcp").exists()
    assert (tmp_path / "landing-assets/site.css").is_file()


def test_published_local_policy_routes_are_valid(landing_config):
    from freeagent_ai.landing import validate_config

    config = dict(landing_config)
    for name in ("privacy", "terms", "support"):
        config[name + "_url"] = "https://freeagent-ai.avalou.co/" + name + "/"
    assert validate_config(config)["privacy_url"] == config["privacy_url"]


def test_hosted_project_must_be_explicit_without_operator_fallback(monkeypatch):
    values = {
        "AUTH0_ISSUER": "https://example.auth0.com/",
        "AUTH0_MCP_CLIENT_ID": "example-mcp-client",
        "AUTH0_WEB_CLIENT_ID": "example-web-client",
        "AUTH0_WEB_CLIENT_SECRET": "test-only",
        "FREEAGENT_CLIENT_ID": "example-upstream-client",
        "FREEAGENT_CLIENT_SECRET": "test-only",
        "FREEAGENT_TOKEN_ENCRYPTION_KEY": json.dumps({"active": "1", "keys": {"1": "test-only"}}),
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    with pytest.raises(ValueError, match="Hosted configuration incomplete"):
        Settings.from_env()
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "example-project")
    assert Settings.from_env().project == "example-project"
