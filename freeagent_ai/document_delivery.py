"""One-file delegated downloads, issued only under the original MCP authorization."""

import json
import re
from dataclasses import dataclass, field

from mcp.types import CallToolResult, TextContent

from .hosted_accounts import AccessDenied, Binding, key_for
from .hosted_auth import MAX_SESSION_SECONDS, ORIGIN
from .pdf_documents import fetch_pdf

UI_URI = "ui://freeagent/document-download-v3.html"
GRANT_TTL = 120
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
COLLECTION_ROOTS = {"invoices": "invoice", "estimates": "estimate", "credit_notes": "credit_note"}


@dataclass
class DownloadOffer:
    metadata: dict
    private: dict = field(repr=False)

    def tool_result(self):
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(self.metadata))],
            structured_content=self.metadata,
            _meta={"document_download": self.private},
        )


def _original(binding, collection, record_id):
    return {
        "subject": binding.subject,
        "company": binding.company,
        "environment": binding.environment,
        "generation": binding.generation,
        "primary_auth_time": binding.primary_auth_time,
        "generation_authorized": binding.generation_authorized,
        "collection": collection,
        "record_id": record_id,
        "scope": "freeagent:read",
    }


def _binding(record):
    return Binding(
        record["subject"],
        record["company"],
        record["environment"],
        record["generation"],
        record["primary_auth_time"],
        record["generation_authorized"],
    )


def _read_state(accounts, token, kind):
    if not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token):
        raise AccessDenied("This document is unavailable. Try Download PDF again.")
    state = accounts.store.get("web_state", key_for(token))
    if (
        state.get("kind") != kind
        or state.get("used")
        or state.get("expires", 0) <= accounts.clock()
        or state.get("scope") != "freeagent:read"
    ):
        raise AccessDenied("This download expired. Try Download PDF again.")
    return state


def _metadata(document, collection, record_id, ttl):
    kind = {"invoices": "Invoice", "estimates": "Estimate", "credit_notes": "Credit note"}[collection]
    return {
        **document.metadata,
        "expires_in_seconds": ttl,
        "document_label": kind + " " + (document.reference or record_id),
    }


def prepare(accounts, binding, client, collection, record_id):
    document = fetch_pdf(client.call, client.base, collection, record_id)
    accounts.check(binding)
    # This context is not a download capability. Every refresh requires current
    # MCP read authorization and an exact immutable original-binding match.
    ttl = max(1, int(binding.primary_auth_time + MAX_SESSION_SECONDS - accounts.clock()))
    context = accounts.new_state(
        "document_context",
        {**_original(binding, collection, record_id), "metadata": _metadata(document, collection, record_id, ttl)},
        ttl=ttl,
    )
    return DownloadOffer(
        _metadata(document, collection, record_id, ttl),
        {"context": context, "refresh_tool": "refresh_" + COLLECTION_ROOTS[collection] + "_pdf"},
    )


def refresh(accounts, current_binding, client, collection, context):
    original = _read_state(accounts, context, "document_context")
    fields = ("subject", "company", "environment", "generation")
    if original["collection"] != collection or any(original[name] != getattr(current_binding, name) for name in fields):
        raise AccessDenied("The connected account changed. Select the document again.")
    binding = _binding(original)
    accounts.check(binding)
    # Authorization is the only work before navigation. The browser redemption
    # performs the fresh provider fetch; these display fields are the original
    # verified snapshot, never a claim that preparation has already completed.
    metadata = original.get("metadata")
    if not isinstance(metadata, dict):
        raise AccessDenied("This document card is out of date. Select the document again.")
    # The browser receives only this 256-bit, two-minute, single-file delegated
    # capability. Its authority is possession, not a browser cookie or login.
    token = accounts.new_state(
        "document_download", _original(binding, collection, original["record_id"]), ttl=GRANT_TTL
    )
    return DownloadOffer(
        {**metadata, "expires_in_seconds": GRANT_TTL},
        {"url": ORIGIN + "/documents#" + token},
    )


def redeem(accounts, token, client_factory):
    grant = _read_state(accounts, token, "document_download")
    binding = _binding(grant)
    accounts.check(binding)
    accounts.limit(binding.subject)
    accounts.take_state(token, "document_download")
    client = client_factory(binding)
    document = fetch_pdf(client.call, client.base, grant["collection"], grant["record_id"])
    accounts.check(binding)
    return document
