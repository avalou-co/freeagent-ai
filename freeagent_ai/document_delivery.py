"""Authenticated one-use browser delivery; state stores metadata, never PDF bytes."""

import json
import re
from dataclasses import dataclass, field

from mcp.types import CallToolResult, TextContent

from .hosted_accounts import AccessDenied, Binding, Principal, key_for
from .hosted_auth import GENERATION_CLAIM, ORIGIN, connection_generation
from .pdf_documents import fetch_pdf

UI_URI = "ui://freeagent/document-download.html"
GRANT_TTL = 120
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


@dataclass
class DownloadOffer:
    metadata: dict
    token: str = field(repr=False)

    def tool_result(self):
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(self.metadata))],
            structured_content=self.metadata,
            _meta={"document_download": {"url": ORIGIN + "/documents#" + self.token}},
        )


def prepare(accounts, binding, client, collection, record_id):
    # Provider content is checked but not persisted. The browser refetches under
    # the original binding at redemption, keeping retention invocation-only.
    document = fetch_pdf(client.call, client.base, collection, record_id)
    accounts.check(binding)
    token = accounts.new_state(
        "document_download",
        {
            "subject": binding.subject,
            "company": binding.company,
            "environment": binding.environment,
            "generation": binding.generation,
            "primary_auth_time": binding.primary_auth_time,
            "generation_authorized": binding.generation_authorized,
            "collection": collection,
            "record_id": record_id,
        },
        ttl=GRANT_TTL,
    )
    return DownloadOffer({**document.metadata, "expires_in_seconds": GRANT_TTL}, token)


def redeem(accounts, session_record, token, client_factory, *, connection_name="freeagent"):
    if not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token):
        raise AccessDenied("Document offer unavailable; request a new PDF in ChatGPT")
    grant = accounts.store.get("web_state", key_for(token))
    if (
        grant.get("kind") != "document_download"
        or grant.get("used")
        or grant.get("expires", 0) <= accounts.clock()
        or grant.get("subject") != session_record.get("subject")
    ):
        raise AccessDenied("Document offer expired or belongs to a different signed-in account")
    # Browser authentication is independent; it cannot supply a new account for
    # the request. Verify both the original and browser authorization context.
    binding = Binding(
        grant["subject"],
        grant["company"],
        grant["environment"],
        grant["generation"],
        grant["primary_auth_time"],
        grant["generation_authorized"],
    )
    accounts.check(binding)
    browser_generation = connection_generation(
        {"sub": session_record["subject"], GENERATION_CLAIM: session_record.get("connection_generation")},
        connection_name,
    )
    browser_binding = accounts.bind(
        Principal(
            session_record["subject"],
            frozenset({"freeagent:read"}),
            session_record["primary_auth_time"],
            browser_generation,
        )
    )
    if (browser_binding.company, browser_binding.environment, browser_binding.generation) != (
        binding.company,
        binding.environment,
        binding.generation,
    ):
        raise AccessDenied("Document account changed; request a new PDF in ChatGPT")
    accounts.limit(binding.subject)
    # Consume atomically before the outbound read; uncertain failures require a
    # new offer. One grant never produces multiple file responses across workers.
    accounts.take_state(token, "document_download")
    client = client_factory(binding)
    document = fetch_pdf(client.call, client.base, grant["collection"], grant["record_id"])
    accounts.check(binding)
    return document
