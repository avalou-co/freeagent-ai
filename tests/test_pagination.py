"""Both transports retain the same completeness and destination guarantees."""

from types import SimpleNamespace

import pytest

from freeagent_ai import client
from freeagent_ai.hosted_client import HostedClient
from freeagent_ai.hosted_deadline import Deadline

BASE = client.BASE


@pytest.fixture(params=["local", "hosted"])
def read(request, monkeypatch):
    queue, seen = [], []

    def fetch(method, path, body=None, *args, **kwargs):
        seen.append(path)
        payload, target = queue.pop(0)
        return payload, {"next": {"url": target}} if target is not None else {}

    if request.param == "local":
        monkeypatch.setattr(client, "_request", fetch)
        call = client.call
    else:
        hosted = HostedClient(None, SimpleNamespace(environment="production"), Deadline(), "", "")

        def hosted_fetch(method, path, body):
            payload, links = fetch(method, path, body)
            return payload, {"Link": f'<{links["next"]["url"]}>; rel="next"'} if links else {}

        monkeypatch.setattr(hosted, "_request", hosted_fetch)
        call = hosted.call
    return lambda path="contacts", **kwargs: call("GET", path, **kwargs), queue, seen


def test_empty_page_still_follows_link_and_preserves_metadata(read):
    call, queue, seen = read
    queue.extend(
        [
            ({"contacts": [], "other": [1], "metadata": "first"}, "?view=all&page=2"),
            ({"contacts": [{"id": 2}], "other": [2], "metadata": "second"}, None),
        ]
    )
    assert call("contacts?view=all") == {"contacts": [{"id": 2}], "other": [1, 2], "metadata": "first"}
    assert seen == ["contacts?view=all", "contacts?view=all&page=2"]


@pytest.mark.parametrize(
    "target",
    [
        "https://attacker.invalid/v2/contacts",
        "//attacker.invalid/v2/contacts",
        "http://api.freeagent.com/v2/contacts",
        "/token_endpoint",
        "contacts/%2e%2e/1",
        "contacts#fragment",
    ],
)
def test_rejected_links_never_reach_transport(read, target):
    call, queue, seen = read
    queue.append(({"contacts": []}, target))
    with pytest.raises(ValueError):
        call()
    assert seen == ["contacts"]


def test_longer_cycle_stops_before_repeated_request(read):
    call, queue, seen = read
    queue.extend([({"contacts": []}, "?page=2"), ({"contacts": []}, "contacts")])
    with pytest.raises(ValueError, match="cycle"):
        call()
    assert seen == ["contacts", "contacts?page=2"]


@pytest.mark.parametrize("payload", [[], 200, {"contacts": None}, {"errors": []}])
def test_malformed_later_page_never_returns_partial_results(read, payload):
    call, queue, _ = read
    queue.extend([({"contacts": [1]}, "?page=2"), (payload, None)])
    with pytest.raises(ValueError):
        call()


def test_page_limit_raises_instead_of_truncating(read):
    call, queue, seen = read
    queue.extend(({"contacts": [page]}, f"?page={page + 1}") for page in range(1, 1001))
    with pytest.raises(ValueError, match="page limit"):
        call()
    assert len(seen) == 1000


def test_manual_page_does_not_follow_or_validate_unused_link(read):
    call, queue, seen = read
    queue.append(({"contacts": []}, "https://attacker.invalid/"))
    assert call(paginate=False) == {"contacts": []}
    assert seen == ["contacts"]
