"""Bounded, DNS-pinned OpenAI receipt downloads; never read hosted filesystem paths."""

import base64
from urllib.parse import urlsplit

from typing_extensions import NotRequired, TypedDict

from .hosted_deadline import Deadline
from .hosted_network import PinnedHTTPS, resolve_public, set_read_timeout, socket_budget


class OpenAIFile(TypedDict):
    download_url: str
    file_id: str
    mime_type: NotRequired[str]
    file_name: NotRequired[str]


def validate_receipt(data: bytes, declared: str | None = None) -> str:
    """Constrain attachments by signature; never render or execute document content."""
    if not data or len(data) > 5 * 1024 * 1024:
        raise ValueError("Receipt must contain between 1 byte and 5 MiB")
    signatures = (
        (b"%PDF-", "application/pdf"),
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"GIF87a", "image/gif"),
        (b"GIF89a", "image/gif"),
    )
    if declared is not None:
        declared = {"application/x-pdf": "application/pdf", "image/x-png": "image/png", "image/jpg": "image/jpeg"}.get(
            declared, declared
        )
    kind = next((mime for signature, mime in signatures if data.startswith(signature)), None)
    if kind is None or declared not in {None, "", "application/octet-stream", kind}:
        raise ValueError("Receipt must be a PDF, PNG, JPEG or GIF matching its declared type")
    return kind


def download(file: OpenAIFile, allowed_hosts: frozenset[str], parent: Deadline):
    parsed = urlsplit(file["download_url"])
    if (
        parsed.scheme != "https"
        or parsed.hostname not in allowed_hosts
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 443}
        or parsed.fragment
        or not file.get("file_id")
    ):
        raise ValueError("Receipt download origin is not approved")
    budget = Deadline(min(10, parent.remaining()))
    addresses = resolve_public(parsed.hostname, budget)
    last = None
    for address in addresses:
        connection = PinnedHTTPS(parsed.hostname, [address], budget)
        try:
            connection.connect()
            assert connection.sock is not None
            with socket_budget(connection.sock, budget):
                connection.sock.settimeout(budget.remaining())
                connection.request(
                    "GET",
                    parsed.path + ("?" + parsed.query if parsed.query else ""),
                    headers={"Accept-Encoding": "identity"},
                )
                connection.sock.settimeout(budget.remaining())
                response = connection.getresponse()
                if response.status != 200 or response.getheader("Content-Encoding", "identity") != "identity":
                    raise ValueError("Receipt download rejected; obtain a fresh file reference")
                limit = 5 * 1024 * 1024
                length = response.getheader("Content-Length")
                if length and int(length) > limit:
                    raise ValueError("Receipt exceeds 5 MiB")
                parts, size = [], 0
                while response.fp is not None:
                    set_read_timeout(response, budget)
                    chunk = response.read1(min(65536, limit + 1 - size))
                    budget.remaining()
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > limit:
                        raise ValueError("Receipt exceeds 5 MiB")
                    parts.append(chunk)
                data = b"".join(parts)
                kind = validate_receipt(data, file.get("mime_type"))
                encoded = base64.b64encode(data).decode()
                if len(encoded) > 7 * 1024 * 1024:
                    raise ValueError("Encoded receipt exceeds transport budget")
                name = file.get("file_name", "receipt").replace("\\", "/").rsplit("/", 1)[-1]
                if not name or any(ord(c) < 32 or ord(c) == 127 for c in name) or len(name) > 255:
                    raise ValueError("Invalid receipt filename")
                return {
                    "file_name": name,
                    "content_type": kind,
                    "data": encoded,
                }
        except (OSError, TimeoutError):
            last = True  # Never retain exceptions that may expose signed URLs.
        finally:
            connection.close()
    if last:
        raise ValueError("Receipt download failed; obtain a fresh file reference") from None
    raise ValueError("Receipt download failed")
