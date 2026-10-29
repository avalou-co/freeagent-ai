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


def test_exported_structured_data_links_publisher_site_and_software(tmp_path):
    import json

    build_static(tmp_path)
    blocks = []

    class StructuredData(HTMLParser):
        collecting = False

        def handle_starttag(self, tag, attrs):
            self.collecting = tag == "script" and dict(attrs).get("type") == "application/ld+json"

        def handle_data(self, data):
            if self.collecting:
                blocks.append(data)

        def handle_endtag(self, tag):
            if tag == "script":
                self.collecting = False

    StructuredData().feed((tmp_path / "index.html").read_text())
    assert len(blocks) == 1
    data = json.loads(blocks[0])
    assert data["@context"] == "https://schema.org"
    entities = {entity["@type"]: entity for entity in data["@graph"]}
    assert set(entities) == {"Organization", "WebSite", "SoftwareApplication"}
    publisher = entities["Organization"]
    website = entities["WebSite"]
    software = entities["SoftwareApplication"]
    assert publisher["name"] == "Avalou"
    assert publisher["url"] == "https://avalou.co"
    assert website["name"] == software["name"] == "FreeAgent AI"
    assert website["url"] == software["url"] == "https://freeagent-ai.avalou.co/"
    assert website["publisher"] == software["publisher"] == {"@id": publisher["@id"]}
    assert website["about"] == {"@id": software["@id"]}
    assert software["applicationCategory"] == "BusinessApplication"
    assert "connector" in software["description"]
    assert not {"offers", "aggregateRating", "review", "installUrl", "downloadUrl"} & software.keys()
