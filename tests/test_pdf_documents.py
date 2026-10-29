"""Synthetic document transport and authenticated HTTP security regressions."""

import base64
import json
import time
import urllib.error
from email.message import Message
from io import BytesIO
from types import SimpleNamespace

import pytest
from conftest import settings
from starlette.testclient import TestClient

from freeagent_ai.hosted_accounts import Principal
from freeagent_ai.hosted_app import create_app
from freeagent_ai.hosted_auth import ORIGIN
from freeagent_ai.hosted_client import HostedClient
from freeagent_ai.pdf_documents import MAX_ENCODED_BYTES, MAX_PDF_BYTES, fetch_pdf
from freeagent_ai.public_tools import Dispatcher, make_registry

BASE = "https://api.freeagent.com/v2/"
PDF = b"%PDF-1.4\nsynthetic transport fixture\n%%EOF\n"


@pytest.fixture
def pdf_remote(accounts, monkeypatch):
    # Preserve prototype security diagnostics without enabling hosted discovery.
    prototype_registry = make_registry(experimental_pdf=True)
    monkeypatch.setattr("freeagent_ai.public_tools.REGISTRY", prototype_registry)
    monkeypatch.setattr("freeagent_ai.hosted_app.REGISTRY", prototype_registry)
    for subject, company in (("alice", "1"), ("bob", "2")):
        accounts.replace(
            subject,
            BASE + "company/" + company,
            "production",
            {"access_token": subject, "expires_at": time.time() + 3600},
            0,
        )
    calls, mode = [], {}

    def transport(method, url, deadline, **kwargs):
        subject = kwargs["headers"]["Authorization"].split()[-1]
        calls.append((subject, method, url))
        if mode.get("denied"):
            raise urllib.error.HTTPError(url, 403, "denied", Message(), BytesIO(b"private provider body"))
        path = url.removeprefix(BASE)
        if path.endswith("/pdf"):
            if mode.get("disconnect"):
                accounts.disconnect(subject, 1)
            return {"pdf": {"content": mode.get("content", base64.encodebytes(PDF).decode())}}, {}
        root = {"invoices": "invoice", "estimates": "estimate", "credit_notes": "credit_note"}[path.split("/")[0]]
        return {root: {"url": BASE + ("invoices/999" if mode.get("wrong_identity") else path)}}, {}

    dispatcher = Dispatcher(
        accounts, "id", "secret", client_factory=lambda *args: HostedClient(*args, transport=transport)
    )
    verifier = SimpleNamespace(
        principal=lambda token: Principal(
            token, frozenset() if token == "denied" else frozenset({"freeagent:read"}), 101
        )
    )
    with TestClient(create_app(settings(), accounts, verifier, dispatcher), base_url=ORIGIN) as client:

        def rpc(name, args=None, token="alice"):
            response = client.post(
                "/mcp",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json, text/event-stream"},
                json={"jsonrpc": "2.0", "id": 1, "method": name, "params": args or {}},
            )
            assert response.status_code == 200
            return response.json()["result"]

        yield rpc, calls, mode


@pytest.mark.parametrize(
    "root,collection", [("invoice", "invoices"), ("estimate", "estimates"), ("credit_note", "credit_notes")]
)
def test_authenticated_pdf_bytes_are_embedded_not_text_or_metadata(pdf_remote, root, collection):
    rpc, calls, _ = pdf_remote
    descriptors = {tool["name"]: tool for tool in rpc("tools/list")["tools"]}
    assert descriptors["get_" + root + "_pdf"]["annotations"]["readOnlyHint"]
    result = rpc("tools/call", {"name": "get_" + root + "_pdf", "arguments": {"id": "7"}})
    assert not result.get("isError")
    metadata = result["structuredContent"]
    assert metadata["source"] == BASE + collection + "/7"
    assert metadata["size_bytes"] == len(PDF)
    assert "blob" not in json.dumps(metadata)
    assert result["content"][0]["text"] == json.dumps(metadata)
    resource = result["content"][1]["resource"]
    assert resource["mimeType"] == "application/pdf"
    assert base64.b64decode(resource["blob"]) == PDF
    assert calls == [("alice", "GET", BASE + collection + "/7"), ("alice", "GET", BASE + collection + "/7/pdf")]


@pytest.mark.parametrize("mode", ["wrong_identity", "denied", "disconnect"])
def test_pdf_refuses_wrong_identity_denial_and_revoked_binding(pdf_remote, mode):
    rpc, calls, state = pdf_remote
    state[mode] = True
    result = rpc("tools/call", {"name": "get_invoice_pdf", "arguments": {"id": "7"}})
    assert result["isError"]
    assert "resource" not in [item["type"] for item in result["content"]]
    assert "private provider body" not in json.dumps(result)
    if mode != "disconnect":
        assert len(calls) == 1


def test_scope_and_numeric_id_rejected_before_provider(pdf_remote):
    rpc, calls, _ = pdf_remote
    for args, token in [
        ({"id": "7"}, "denied"),
        ({"id": "../7"}, "alice"),
        ({"id": "https://evil.invalid/7"}, "alice"),
    ]:
        assert rpc("tools/call", {"name": "get_invoice_pdf", "arguments": args}, token)["isError"]
    assert not calls


def test_two_accounts_fetch_with_their_own_bound_credentials(pdf_remote):
    rpc, calls, _ = pdf_remote
    for token in ["alice", "bob"]:
        result = rpc("tools/call", {"name": "get_invoice_pdf", "arguments": {"id": "7"}}, token)
        assert not result.get("isError")
    assert [subject for subject, _, _ in calls] == ["alice", "alice", "bob", "bob"]


@pytest.mark.parametrize(
    "content",
    [
        "!invalid!",
        "é",
        "",
        base64.b64encode(b"not PDF").decode(),
        base64.b64encode(b"%PDF-1.4\ntruncated").decode(),
        "A" * (MAX_ENCODED_BYTES + 1),
        base64.b64encode(b"%PDF-1.4\n" + b"x" * MAX_PDF_BYTES + b"%%EOF").decode(),
    ],
)
def test_malformed_and_oversized_provider_data_never_reaches_resource(pdf_remote, content):
    rpc, _, mode = pdf_remote
    mode["content"] = content
    result = rpc("tools/call", {"name": "get_invoice_pdf", "arguments": {"id": "7"}})
    assert result["isError"]
    assert len(result["content"]) == 1
    assert len(json.dumps(result)) < 1000


def test_local_fixed_fetch_contract():
    calls = []

    def call(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return (
            {"invoice": {"url": BASE + "invoices/1"}}
            if path == "invoices/1"
            else {"pdf": {"content": base64.encodebytes(PDF).decode()}}
        )

    result = fetch_pdf(call, BASE, "invoices", "1").tool_result()
    assert result.structured_content["file_name"] == "invoices-1.pdf"
    assert calls == [("GET", "invoices/1", {}), ("GET", "invoices/1/pdf", {"paginate": False})]


def test_shipped_document_transport_is_registered_ui_not_prototype_blob():
    from pathlib import Path

    from freeagent_ai.document_delivery import UI_URI
    from freeagent_ai.public_package import package_files
    from freeagent_ai.public_tools import REGISTRY

    assert not any(op.root == "pdf" for op in REGISTRY.values())
    for name in ("get_invoice_pdf", "get_estimate_pdf", "get_credit_note_pdf"):
        assert REGISTRY[name].root == "document_download"
        assert REGISTRY[name].descriptor.meta["ui"]["resourceUri"] == UI_URI
    files = package_files(Path(__file__).resolve().parents[1])
    assert "skills/documents/SKILL.md" in files
    contract = json.loads(files["docs/capabilities.json"])["documents"]
    assert contract["output_artifacts"] == ["registered MCP Apps UI -> same-account HTTPS application/pdf attachment"]
    assert (
        json.loads(files["docs/unsupported-capabilities.json"])["documents"]["status"]
        == "awaiting_installed_client_verification"
    )


def test_package_gate_rejects_pdf_reenablement_and_missing_status(monkeypatch):
    from pathlib import Path

    from freeagent_ai.package_contract import validate_contract, validate_operations
    from freeagent_ai.public_package import package_files
    from freeagent_ai.public_tools import REGISTRY

    files = package_files(Path(__file__).resolve().parents[1])
    del files["docs/unsupported-capabilities.json"]
    with pytest.raises(ValueError, match="Unsupported capability status"):
        validate_contract(files)
    prototype = make_registry(experimental_pdf=True)["get_invoice_pdf"]
    monkeypatch.setitem(REGISTRY, "get_invoice_pdf", prototype)
    with pytest.raises(ValueError, match="Non-provider operation"):
        validate_operations()


@pytest.mark.parametrize("builder", ["draft", "operator"])
def test_both_archive_builders_refuse_pdf_registry_reenablement(monkeypatch, tmp_path, builder):
    import runpy
    from pathlib import Path

    from freeagent_ai.public_package import build
    from freeagent_ai.public_tools import REGISTRY

    operator_build = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/package_hosted_plugin.py"))[
        "build"
    ]

    monkeypatch.setitem(REGISTRY, "get_invoice_pdf", make_registry(experimental_pdf=True)["get_invoice_pdf"])
    output = tmp_path / "blocked.zip"
    with pytest.raises(ValueError, match="Non-provider operation|Unsupported file-output"):
        if builder == "draft":
            build(Path(__file__).resolve().parents[1], output, draft=True)
        else:
            operator_build(output, "synthetic-client")
    assert not output.exists()
