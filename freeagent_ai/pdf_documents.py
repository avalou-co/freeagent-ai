"""Bounded, invocation-only PDF transport. No file store, public URLs or logging."""

import base64
import binascii
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from mcp.types import BlobResourceContents, CallToolResult, EmbeddedResource, TextContent

MAX_PDF_BYTES = 5 * 1024 * 1024
# RFC 2045 permits line wrapping. Bound the original envelope before decoding.
MAX_ENCODED_BYTES = 8 * 1024 * 1024


@dataclass
class PdfDocument:
    metadata: dict
    data: bytes = field(repr=False)

    def tool_result(self):
        return CallToolResult(
            content=[
                TextContent(type="text", text=json.dumps(self.metadata)),
                EmbeddedResource(
                    type="resource",
                    resource=BlobResourceContents(
                        uri="freeagent-pdf:///" + uuid4().hex + "/" + self.metadata["file_name"],
                        mime_type="application/pdf",
                        blob=base64.b64encode(self.data).decode("ascii"),
                    ),
                ),
            ],
            structured_content=self.metadata,
        )


def fetch_pdf(call, base, collection, record_id):
    """Fetch fixed endpoints through the already account-bound client only."""
    roots = {"invoices": "invoice", "estimates": "estimate", "credit_notes": "credit_note"}
    if collection not in roots or not isinstance(record_id, str) or not re.fullmatch(r"[0-9]+", record_id):
        raise ValueError("Expected a supported document and numeric ID")
    path = collection + "/" + record_id
    # Read identity under the same binding before asking for its PDF. No caller URLs.
    result = call("GET", path)
    record = result.get(roots[collection]) if isinstance(result, dict) else None
    if not isinstance(record, dict) or record.get("url") != base + path:
        raise ValueError("Document identity was not verified")
    response = call("GET", path + "/pdf", paginate=False)
    pdf = response.get("pdf") if isinstance(response, dict) else None
    content = pdf.get("content") if isinstance(pdf, dict) else None
    if not isinstance(content, str) or len(content) > MAX_ENCODED_BYTES:
        raise ValueError("Missing or oversized PDF payload")
    try:
        # Only RFC 2045 whitespace is accepted; other non-base64 bytes fail closed.
        compact = re.sub(r"[ \t\r\n]", "", content).encode("ascii")
        data = base64.b64decode(compact, validate=True)
    except (UnicodeError, binascii.Error):
        raise ValueError("Malformed PDF encoding") from None
    if not data or len(data) > MAX_PDF_BYTES:
        raise ValueError("Empty or oversized PDF")
    # Envelope sanity checks, not a complete PDF parser or malware scanner.
    if not re.match(rb"%PDF-1\.[0-9][\r\n]", data) and not data.startswith(b"%PDF-2.0\n"):
        raise ValueError("Malformed PDF header")
    if not data.rstrip().endswith(b"%%EOF"):
        raise ValueError("Incomplete PDF")
    return PdfDocument(
        {
            "source": base + path,
            "file_name": collection + "-" + record_id + ".pdf",
            "mime_type": "application/pdf",
            "size_bytes": len(data),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        },
        data,
    )
