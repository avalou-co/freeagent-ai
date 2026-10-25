"""Versioned attachment API mechanics using authenticated synthetic transports."""

import json
import time
import urllib.error
from email.message import Message
from io import BytesIO
from typing import Any

import pytest
from mcp.types import TextContent

from freeagent_ai.client import API_VERSION
from freeagent_ai.hosted_accounts import AccessDenied, Principal
from freeagent_ai.hosted_client import HostedClient
from freeagent_ai.public_tools import REGISTRY, Dispatcher

BASE = "https://api.freeagent.com/v2/"
PATH = "bank_transaction_explanations/91/attachments"
FILE = {"download_url": "https://files.example/synthetic?signature=private", "file_id": "file-synthetic"}
ENCODED = {"file_name": "synthetic.png", "content_type": "image/png", "data": "synthetic-base64"}
SAFE = {"url": BASE + "attachments/7", "file_name": "synthetic.png", "file_size": 8, "content_type": "image/png"}
PRIVATE = {**SAFE, "content_src": "https://files.example/private?signature=secret", "data": "private-bytes"}


@pytest.fixture
def principal(accounts):
    accounts.replace(
        "attachment-reviewer",
        BASE + "company/1",
        "production",
        {"access_token": "synthetic", "expires_at": time.time() + 3600},
        0,
    )
    return Principal("attachment-reviewer", frozenset({"freeagent:read", "freeagent:write"}), 101)


def dispatcher(accounts, transport):
    return Dispatcher(accounts, "id", "secret", client_factory=lambda *args: HostedClient(*args, transport=transport))


@pytest.mark.parametrize("count", [0, 1, 3])
@pytest.mark.parametrize("shape", ["legacy", "plural", "nested"])
def test_versioned_and_legacy_bank_reads_preserve_safe_attachment_evidence(
    accounts, principal, hosted_context, count, shape
):
    record: dict = {"url": BASE + "bank_transaction_explanations/91"}
    if shape == "legacy":
        record["attachment"] = PRIVATE if count else None
    else:
        record["attachments"] = [PRIVATE] * count
    operation = "get_bank_transaction_explanation"
    root = "bank_transaction_explanation"
    if shape == "nested":
        record = {"url": BASE + "bank_transactions/22", "bank_transaction_explanations": [record]}
        operation, root = "get_bank_transaction", "bank_transaction"

    def transport(method, url, deadline, **kwargs):
        assert kwargs["headers"]["X-Api-Version"] == API_VERSION == "2026-09-01"
        return {root: record}, {}

    with hosted_context(principal):
        result = dispatcher(accounts, transport).invoke(operation, {"id": "91"})
    projected: Any = result[root]
    if shape == "nested":
        projected = projected["bank_transaction_explanations"][0]
    assert projected == {
        "url": BASE + "bank_transaction_explanations/91",
        **({"attachment": SAFE if count else None} if shape == "legacy" else {"attachments": [SAFE] * count}),
    }
    assert "signature" not in json.dumps(result) and "private-bytes" not in json.dumps(result)


def test_attachment_collection_paginates_and_projects(accounts, principal, hosted_context):
    calls = []

    def transport(method, url, deadline, **kwargs):
        calls.append(url)
        assert kwargs["headers"]["X-Api-Version"] == API_VERSION
        return {"attachments": [PRIVATE]}, ({"Link": f'<{BASE + PATH}?page=2>; rel="next"'} if len(calls) == 1 else {})

    with hosted_context(principal):
        result = dispatcher(accounts, transport).invoke("list_bank_transaction_explanation_attachments", {"id": "91"})
    assert result == {"attachments": [SAFE, SAFE]}
    assert calls == [BASE + PATH, BASE + PATH + "?page=2"]


@pytest.mark.parametrize("action", ["add", "update", "remove"])
def test_attachment_writes_use_fixed_endpoint_and_verified_readback(
    accounts, principal, hosted_context, monkeypatch, action
):
    calls, downloads = [], []
    monkeypatch.setattr("freeagent_ai.public_tools.download", lambda file, *_: downloads.append(file) or ENCODED)
    args = {"id": "91", "confirmed": True}
    if action != "remove":
        args.update(file=FILE, description="Reviewed synthetic receipt")
    if action != "add":
        args["attachment_id"] = "7"
    actual = [] if action == "remove" else [{**PRIVATE, "description": "Provider returned description"}]

    def transport(method, url, deadline, **kwargs):
        calls.append((method, url, kwargs["body"]))
        assert kwargs["headers"]["X-Api-Version"] == API_VERSION
        return {"attachments": actual}, {}

    name = action + "_bank_transaction_explanation_attachment"
    with hosted_context(principal):
        result = dispatcher(accounts, transport).invoke(name, args)
    expected = {"_destroy": "true"} if action == "remove" else {**ENCODED, "description": "Reviewed synthetic receipt"}
    if action != "add":
        expected["url"] = BASE + "attachments/7"
    assert calls == [
        ("POST" if action == "add" else "PUT", BASE + PATH, {"attachments": [expected]}),
        ("GET", BASE + PATH, None),
    ]
    assert downloads == ([] if action == "remove" else [FILE])
    assert result == {
        "attachments": [] if action == "remove" else [{**SAFE, "description": "Provider returned description"}]
    }
    assert "private" not in json.dumps(result)
    assert REGISTRY[name].descriptor.annotations.destructive_hint is (action != "add")


def test_metadata_update_needs_no_file_download(accounts, principal, hosted_context, monkeypatch):
    monkeypatch.setattr("freeagent_ai.public_tools.download", lambda *_: pytest.fail("metadata-only"))
    calls = []

    def transport(method, url, deadline, **kwargs):
        calls.append((method, kwargs["body"]))
        return {"attachments": [PRIVATE]}, {}

    with hosted_context(principal):
        dispatcher(accounts, transport).invoke(
            "update_bank_transaction_explanation_attachment",
            {
                "id": "91",
                "attachment_id": "7",
                "description": "",
                "confirmed": True,
            },
        )
    assert calls[0] == ("PUT", {"attachments": [{"url": BASE + "attachments/7", "description": ""}]})


@pytest.mark.parametrize("case", ["refused", "read_scope", "wrong_subject", "bad_source", "disconnect"])
def test_attachment_upload_denied_before_provider_call(accounts, principal, hosted_context, monkeypatch, case):
    caller = principal
    args = {"id": "91", "confirmed": True, "file": FILE}
    if case == "refused":
        args["confirmed"] = False
    elif case == "read_scope":
        caller = Principal(principal.subject, frozenset({"freeagent:read"}), 101)
    elif case == "wrong_subject":
        caller = Principal("unlinked-subject", principal.scopes, 101)
    elif case == "disconnect":

        def download(*_):
            accounts.disconnect(principal.subject, 1)
            return ENCODED

        monkeypatch.setattr("freeagent_ai.public_tools.download", download)
    client = dispatcher(accounts, lambda *_args, **_kwargs: pytest.fail("provider must not run"))
    with hosted_context(caller), pytest.raises((AccessDenied, ValueError)):
        client.invoke("add_bank_transaction_explanation_attachment", args)


@pytest.mark.parametrize("failure", ["write_timeout", "read_timeout", "malformed_readback", "denied", "validation"])
def test_failed_attachment_write_or_readback_is_not_replayed_or_exposed(
    accounts, principal, hosted_context, monkeypatch, failure
):
    calls = []
    monkeypatch.setattr("freeagent_ai.public_tools.download", lambda *_: ENCODED)

    def transport(method, url, deadline, **kwargs):
        calls.append(method)
        if failure == "write_timeout" and method == "POST" or failure == "read_timeout" and method == "GET":
            raise TimeoutError("private source URL or bytes")
        if failure in {"denied", "validation"}:
            raise urllib.error.HTTPError(
                url,
                403 if failure == "denied" else 422,
                "private",
                Message(),
                BytesIO(b'{"errors":"private-bytes signature=private"}'),
            )
        return (
            {"attachments": "invalid"}
            if method == "GET" and failure == "malformed_readback"
            else {"attachments": [PRIVATE]}
        ), {}

    with hosted_context(principal):
        result = dispatcher(accounts, transport).call_tool(
            "add_bank_transaction_explanation_attachment", {"id": "91", "confirmed": True, "file": FILE}
        )
    assert result.is_error
    assert isinstance(result.content[0], TextContent)
    text = result.content[0].text
    assert "private" not in text and "signature" not in text
    assert calls == (["POST"] if failure in {"write_timeout", "denied", "validation"} else ["POST", "GET"])
    assert "retry" in text or "verified" in text


def test_oauth_refresh_does_not_get_resource_version_header(accounts, principal):
    from freeagent_ai.hosted_deadline import Deadline

    seen = []

    def transport(method, url, deadline, **kwargs):
        seen.append(kwargs["headers"])
        return {"access_token": "synthetic", "expires_in": 3600}, {}

    client = HostedClient(accounts, accounts.bind(principal), Deadline(), "id", "secret", transport=transport)
    assert client.exchange({"refresh_token": "synthetic"})["access_token"] == "synthetic"
    assert len(seen) == 1 and "X-Api-Version" not in seen[0]


@pytest.mark.parametrize("value", [None, "invalid", {}, [None]])
def test_malformed_attachment_collection_is_explicitly_incomplete(accounts, principal, hosted_context, value):
    with hosted_context(principal):
        result = dispatcher(accounts, lambda *_args, **_kwargs: ({"attachments": value}, {})).call_tool(
            "list_bank_transaction_explanation_attachments", {"id": "91"}
        )
    assert result.is_error
    assert isinstance(result.content[0], TextContent)
    assert "Read incomplete" in result.content[0].text
