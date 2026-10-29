"""Real Chromium UI -> HTTPS receiver -> native attachment with synthetic host.

The OpenAI host adapter and network are fixtures, not installed ChatGPT evidence.
No agent interpreter or user-local runtime is involved in the product journey.
"""

import os

import pytest
from test_document_delivery import PDF

from freeagent_ai.document_delivery import UI_URI
from freeagent_ai.hosted_auth import ORIGIN

pytest_plugins = ("test_document_delivery",)

sync_api = pytest.importorskip("playwright.sync_api")


@pytest.fixture(params=["desktop", "mobile"])
def browser_context(request):
    with sync_api.sync_playwright() as runtime:
        executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        browser = runtime.chromium.launch(headless=True, **({"executable_path": executable} if executable else {}))
        mobile = (
            {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True}
            if request.param == "mobile"
            else {}
        )
        with browser.new_context(accept_downloads=True, **mobile) as context:
            yield context
        browser.close()


def mount(browser_context, d, *, account="alice", host_supported=True):
    resource = d.rpc("resources/read", {"uri": UI_URI})["contents"][0]
    urls = []
    d.browser_responses = []

    def route(request_route):
        request = request_route.request
        urls.append(request.url)
        if request.url.startswith(ORIGIN):
            response = d.client.request(
                request.method, request.url, headers=request.all_headers(), content=request.post_data_buffer
            )
            d.browser_responses.append(
                (
                    request.method,
                    response.status_code,
                    response.headers.get("content-type"),
                    response.text if response.status_code != 200 else "ok",
                )
            )
            request_route.fulfill(status=response.status_code, headers=dict(response.headers), body=response.content)
        else:
            request_route.fulfill(status=200, content_type="text/html", body=resource["text"])

    browser_context.route("**/*", route)
    if account:
        browser_context.add_cookies(
            [
                {
                    "name": "__session",
                    "value": d.cookies[account],
                    "url": ORIGIN,
                    "secure": True,
                    "httpOnly": True,
                    "sameSite": "Lax",
                }
            ]
        )
    if host_supported:
        browser_context.add_init_script(
            "window.openai={openExternal:({href,redirectUrl})=>{if(redirectUrl!==false)throw Error('Invalid navigation');window.open(href,'_blank','noopener');}};"
        )
    page = browser_context.new_page()
    page.goto("https://widget.example.invalid/")
    result = d.offer()
    page.evaluate(
        "result => window.postMessage({jsonrpc:'2.0',method:'ui/notifications/tool-result',params:result},'*')", result
    )
    return page, urls


def test_registered_widget_native_download_without_client_interpreter(delivery, browser_context, tmp_path):
    page, urls = mount(browser_context, delivery)
    with browser_context.expect_page() as popup:
        page.get_by_role("button", name="Download PDF").click()
    receiver = popup.value
    receiver.wait_for_load_state()
    assert receiver.url == ORIGIN + "/documents"
    original_token = receiver.locator("#grant").input_value()
    assert original_token
    try:
        with receiver.expect_download(timeout=5000) as downloading:
            receiver.get_by_role("button", name="Download PDF").click()
    except sync_api.TimeoutError:
        pytest.fail(repr(delivery.browser_responses) + receiver.locator("body").inner_text())
    download = downloading.value
    assert download.suggested_filename == "invoices-7.pdf"
    output = tmp_path / download.suggested_filename
    download.save_as(output)
    assert output.read_bytes() == PDF
    assert receiver.locator("#grant").input_value() == ""
    assert all("#" not in url and "grant=" not in url for url in urls)
    assert receiver.evaluate("Object.keys(localStorage).length + Object.keys(sessionStorage).length") == 0
    assert receiver.get_by_role("button", name="Download PDF").is_disabled()
    replay = browser_context.new_page()
    replay.goto(ORIGIN + "/documents#" + original_token)
    replay.get_by_role("button", name="Download PDF").click()
    replay.get_by_text("Document offer expired or belongs to a different signed-in account").wait_for()


def test_host_without_navigation_reports_unavailable(delivery, browser_context):
    page, _ = mount(browser_context, delivery, host_supported=False)
    assert page.get_by_text("This host cannot open the secure document download.", exact=False).is_visible()
    assert page.get_by_role("button", name="Download PDF").is_hidden()


def test_wrong_browser_account_cannot_receive_attachment(delivery, browser_context):
    page, _ = mount(browser_context, delivery, account="bob")
    with browser_context.expect_page() as popup:
        page.get_by_role("button", name="Download PDF").click()
    receiver = popup.value
    receiver.wait_for_load_state()
    downloads = []
    receiver.on("download", lambda value: downloads.append(value))
    receiver.get_by_role("button", name="Download PDF").click()
    receiver.wait_for_url(ORIGIN + "/documents/download")
    assert receiver.get_by_text("Document offer expired or belongs to a different signed-in account").is_visible()
    assert not downloads
    assert all(subject == "alice" for subject, _, _ in delivery.calls)
