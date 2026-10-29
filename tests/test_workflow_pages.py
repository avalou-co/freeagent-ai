from html import unescape
from html.parser import HTMLParser
from xml.etree import ElementTree

from freeagent_ai.landing import ASSET_PREFIX, build_static
from freeagent_ai.workflow_pages import WORKFLOWS, render_workflow


class Page(HTMLParser):
    def __init__(self, document):
        super().__init__()
        self.links = []
        self.canonicals = []
        self.descriptions = []
        self.headings = 0
        self.feed(document)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "a":
            self.links.append(values["href"])
        if tag == "h1":
            self.headings += 1
        if tag == "link" and values.get("rel") == "canonical":
            self.canonicals.append(values["href"])
        if tag == "meta" and values.get("name") == "description":
            self.descriptions.append(values["content"])


def test_workflow_pages_are_discoverable_and_links_resolve(tmp_path):
    build_static(tmp_path)
    homepage = Page((tmp_path / "index.html").read_text())
    sitemap = ElementTree.parse(tmp_path / "sitemap.xml")
    locations = {node.text for node in sitemap.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")}
    titles, descriptions = set(), set()
    assert len(WORKFLOWS) == 7
    for slug, workflow in WORKFLOWS.items():
        path = f"/workflows/{slug}/"
        assert path in homepage.links
        assert "https://freeagent-ai.avalou.co" + path in locations
        document = (tmp_path / path.strip("/") / "index.html").read_text()
        assert document == render_workflow(slug, ASSET_PREFIX)
        page = Page(document)
        assert page.headings == 1
        assert page.canonicals == ["https://freeagent-ai.avalou.co" + path]
        assert page.descriptions == [workflow.description]
        assert workflow.prompt in unescape(document)
        titles.add(workflow.title)
        descriptions.add(workflow.description)
        for link in page.links:
            if link.startswith("/"):
                target = link.split("#")[0]
                assert (tmp_path / target.strip("/") / "index.html").is_file()
        assert set(f"/workflows/{other}/" for other in WORKFLOWS if other != slug) <= set(page.links)
    assert len(titles) == len(descriptions) == 7
