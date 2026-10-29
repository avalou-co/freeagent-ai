"""Check that exported social metadata points to the shipped image."""

import struct
from html.parser import HTMLParser
from urllib.parse import urlsplit

from freeagent_ai.landing import build_static


def test_exported_social_card_is_available_at_its_declared_size(tmp_path):
    build_static(tmp_path)
    metadata = {}

    class Metadata(HTMLParser):
        def handle_starttag(self, tag, attrs):
            attributes = dict(attrs)
            if tag == "meta":
                metadata[attributes.get("property") or attributes.get("name")] = attributes.get("content")

    Metadata().feed((tmp_path / "index.html").read_text())
    assert metadata["og:site_name"] == "FreeAgent AI"
    assert metadata["twitter:card"] == "summary_large_image"
    assert metadata["og:image"] == metadata["twitter:image"]
    url = urlsplit(metadata["og:image"])
    assert (url.scheme, url.netloc) == ("https", "freeagent-ai.avalou.co")
    image = (tmp_path / url.path.lstrip("/")).read_bytes()
    assert image[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", image[16:24]) == (1200, 630)
    assert (metadata["og:image:width"], metadata["og:image:height"]) == ("1200", "630")
    assert metadata["og:image:type"] == "image/png"
    assert metadata["og:image:alt"] == metadata["twitter:image:alt"]
    assert metadata["og:image:alt"]
