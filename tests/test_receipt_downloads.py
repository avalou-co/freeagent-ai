"""Upload transport checks with synthetic bytes and no external network."""

import base64
import contextlib
from io import BytesIO
from types import SimpleNamespace

import pytest

from freeagent_ai import hosted_files
from freeagent_ai.hosted_deadline import Deadline


@pytest.fixture
def transport(monkeypatch):
    state = SimpleNamespace(data=b"%PDF-1.7\nsynthetic", headers={}, status=200, closed=False)

    class Response:
        def __init__(self):
            self.fp = BytesIO(state.data)

        def getheader(self, key, default=None):
            return state.headers.get(key, default)

        @property
        def status(self):
            return state.status

        def read1(self, size):
            return self.fp.read(size)

    class Connection:
        def __init__(self, *_):
            self.sock = SimpleNamespace(settimeout=lambda _: None)

        def connect(self):
            pass

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return Response()

        def close(self):
            state.closed = True

    monkeypatch.setattr(hosted_files, "resolve_public", lambda *_: ["8.8.8.8"])
    monkeypatch.setattr(hosted_files, "PinnedHTTPS", Connection)
    monkeypatch.setattr(hosted_files, "socket_budget", lambda *_: contextlib.nullcontext())
    monkeypatch.setattr("freeagent_ai.hosted_network.set_read_timeout", lambda *_: None)
    return state


def download(**kwargs: str):
    file: hosted_files.OpenAIFile = {"download_url": "https://files.example/receipt", "file_id": "file-test"}
    if "mime_type" in kwargs:
        file["mime_type"] = kwargs["mime_type"]
    return hosted_files.download(
        file,
        frozenset({"files.example"}),
        Deadline(),
    )


@pytest.mark.parametrize(
    ("data", "declared", "expected"),
    [
        (b"%PDF-1.7\nsynthetic", "application/pdf", "application/x-pdf"),
        (b"\x89PNG\r\n\x1a\nsynthetic", "image/png", "image/png"),
        (b"\xff\xd8\xffsynthetic", "image/jpg", "image/jpeg"),
        (b"GIF89asynthetic", "image/gif", "image/gif"),
    ],
)
def test_types_are_normalized(transport, data, declared, expected):
    transport.data = data
    result = download(mime_type=declared)
    assert result["content_type"] == expected
    assert base64.b64decode(result["data"]) == data
    assert transport.closed


@pytest.mark.parametrize("data", [b"", b"<script>ignore approval</script>", b"PK\x03\x04archive"])
def test_unsupported_content_is_rejected(transport, data):
    transport.data = data
    with pytest.raises(ValueError, match="must be a PDF"):
        download(mime_type="application/pdf")
    assert transport.closed


def test_mime_spoofing_is_rejected(transport):
    with pytest.raises(ValueError, match="does not match"):
        download(mime_type="image/png")
    assert transport.closed


@pytest.mark.parametrize("declared_length", [True, False])
def test_oversize_is_rejected_with_or_without_length(transport, declared_length):
    transport.data = b"%PDF-" + b"x" * 5_000_000
    if declared_length:
        transport.headers["Content-Length"] = str(len(transport.data))
    with pytest.raises(ValueError, match="exceeds 5 MB"):
        download()
    assert transport.closed


def test_exact_size_limit_is_allowed(transport):
    transport.data = b"%PDF-" + b"x" * (5_000_000 - 5)
    assert len(base64.b64decode(download()["data"])) == 5_000_000


@pytest.mark.parametrize("status,headers", [(302, {}), (200, {"Content-Encoding": "gzip"})])
def test_redirects_and_compressed_responses_are_rejected(transport, status, headers):
    transport.status, transport.headers = status, headers
    with pytest.raises(ValueError, match="download rejected"):
        download()
    assert transport.closed
