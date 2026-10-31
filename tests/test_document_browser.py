"""Real Chromium one-action PDF UX with documented host adapters and synthetic API.

These browser fixtures are not evidence from an installed ChatGPT client.
"""

import json
import os
from pathlib import Path

import pytest
from test_document_delivery import PDF

from freeagent_ai.document_delivery import UI_URI
from freeagent_ai.hosted_auth import ORIGIN

pytest_plugins = ("test_document_delivery", "test_document_connect")
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


def mount(browser_context, d, *, host_supported=True, cookie=""):
    resource = d.rpc("resources/read", {"uri": UI_URI})["contents"][0]
    urls, refreshes, grant_urls, downloads = [], [], [], []
    browser_context.on("page", lambda page: page.on("download", lambda download: downloads.append(download)))
    hosting = json.loads((Path(__file__).parents[1] / "hosting.json").read_text())
    edge_headers = {
        key.lower(): value
        for rule in hosting["headers"]
        if rule["glob"] == "**"
        for key, value in rule["headers"].items()
    }

    def route(request_route):
        request = request_route.request
        urls.append(request.url)
        if request.url.startswith(ORIGIN):
            response = d.client.request(
                request.method, request.url, headers=request.all_headers(), content=request.post_data_buffer
            )
            if request.url == ORIGIN + "/documents/download" and response.status_code == 200:
                assert response.headers["referrer-policy"] == "no-referrer"
            # Hosting applies its global headers after the rewritten backend response.
            # Exercise the same boundary that can otherwise block the receiver script.
            request_route.fulfill(
                status=response.status_code, headers={**response.headers, **edge_headers}, body=response.content
            )
        else:
            request_route.fulfill(status=200, content_type="text/html", body=resource["text"])

    browser_context.route("**/*", route)
    if cookie:
        browser_context.add_cookies(
            [{"name": "__session", "value": cookie, "url": ORIGIN, "secure": True, "httpOnly": True}]
        )
    page = browser_context.new_page()

    def host_rpc(method, params):
        if method == "ui/initialize":
            return {"hostContext": {"theme": "light"}}
        assert method == "tools/call"
        refreshes.append(params)
        result = d.rpc(method, params)
        url = result.get("_meta", {}).get("document_download", {}).get("url")
        if url:
            grant_urls.append(url)
        return result

    page.expose_function("__hostRpc", host_rpc)
    browser_context.add_init_script("""
      window.addEventListener("message",async event=>{
        const m=event.data;
        if(event.source!==window||m?.jsonrpc!=="2.0"||!["ui/initialize","tools/call"].includes(m.method))return;
        const result=await window.__hostRpc(m.method,m.params);
        window.postMessage({jsonrpc:"2.0",id:m.id,result},"*");
      });
    """)
    if host_supported:
        browser_context.add_init_script(
            "window.openai={openExternal:({href,redirectUrl})=>{if(redirectUrl!==false)throw Error('Invalid navigation');window.open(href,'_blank','noopener');}};"
        )
    page.goto("https://widget.example.invalid/")
    result = d.offer()
    page.evaluate(
        "result => window.postMessage({jsonrpc:'2.0',method:'ui/notifications/tool-result',params:result},'*')", result
    )
    return page, urls, refreshes, grant_urls, downloads


def wait_download(receiver, downloads):
    for _ in range(100):
        if downloads:
            return downloads[-1]
        receiver.wait_for_timeout(50)
    pytest.fail("The browser did not receive a PDF attachment")


@pytest.mark.parametrize("elapsed,cookie", [(0, ""), (4 * 3600, "different-browser-account")])
def test_single_action_identified_pdf_auto_download_stale_refresh_and_replay(
    connected_delivery, browser_context, tmp_path, elapsed, cookie
):
    d = connected_delivery
    page, urls, refreshes, grant_urls, downloads = mount(browser_context, d, cookie=cookie)
    button = page.get_by_role("button", name="Download PDF")
    sync_api.expect(button).to_be_enabled()
    assert page.get_by_role("button").count() == 1
    assert page.get_by_role("heading", name="Invoice INV-007").is_visible()
    assert not refreshes  # Preparation does not mint a bearer download capability.
    if not elapsed:
        directory = os.environ.get("FREEAGENT_UX_SCREENSHOT_DIR")
        if directory:
            Path(directory).mkdir(parents=True, exist_ok=True)
            name = "mobile" if page.viewport_size["width"] == 390 else "desktop"
            page.locator("main").screenshot(path=str(Path(directory) / (name + ".png")))
    d.now[0] += elapsed
    with browser_context.expect_page() as opened:
        button.click()
    receiver = opened.value
    download = wait_download(receiver, downloads)
    assert download.suggested_filename == "invoices-7.pdf"
    output = tmp_path / download.suggested_filename
    download.save_as(output)
    assert output.read_bytes() == PDF
    assert page.get_by_text("Browser download requested. Check your browser for the PDF or Save dialog.").is_visible()
    assert len(refreshes) == 1 and len(downloads) == 1
    assert receiver.get_by_role("button").count() == 0
    assert receiver.get_by_role("link").count() == 0
    assert receiver.url == ORIGIN + "/documents"
    assert receiver.locator("#grant").input_value() == ""
    assert all("#" not in url and "grant=" not in url and "/login" not in url for url in urls)
    assert receiver.evaluate("Object.keys(localStorage).length+Object.keys(sessionStorage).length") == 0
    replay = browser_context.new_page()
    replay.goto(grant_urls[0])
    replay.get_by_text("This download expired. Try Download PDF again.").wait_for()
    assert len(downloads) == 1


def test_unsupported_host_has_clear_inline_error_without_extra_flow(delivery, browser_context):
    page, urls, refreshes, _, _ = mount(browser_context, delivery, host_supported=False)
    assert page.get_by_text("Downloads aren’t supported in this client.").is_visible()
    assert page.get_by_role("button", name="Download PDF").is_disabled()
    assert not refreshes and not any(url.startswith(ORIGIN) for url in urls)


def test_refused_refresh_stays_inline_and_never_opens_other_account(delivery, browser_context):
    page, urls, refreshes, _, downloads = mount(browser_context, delivery)
    button = page.get_by_role("button", name="Download PDF")
    sync_api.expect(button).to_be_enabled()
    delivery.accounts.disconnect("oauth2|freeagent|alice", 1)
    button.click()
    page.get_by_text("Couldn’t open this PDF. Try again, or check the connected account.").wait_for()
    assert len(refreshes) == 1 and not downloads
    assert not any(url.startswith(ORIGIN) for url in urls)
    assert button.is_enabled()
    assert page.get_by_role("heading", name="Invoice INV-007").is_visible()


@pytest.mark.parametrize("refusal", ["throw", "reject"])
def test_refused_external_navigation_is_inline_without_automatic_retry(delivery, browser_context, refusal):
    page, urls, refreshes, _, downloads = mount(browser_context, delivery)
    page.evaluate(
        """refusal=>{window.openai.openExternal=()=>{
          if(refusal==='throw')throw Error('Host declined navigation');
          return Promise.reject(Error('Host declined navigation'));
        };}""",
        refusal,
    )
    button = page.get_by_role("button", name="Download PDF")
    sync_api.expect(button).to_be_enabled()
    button.click()
    page.get_by_text("Couldn’t open this PDF. Try again, or check the connected account.").wait_for()
    assert len(refreshes) == 1 and not downloads
    assert not any(url.startswith(ORIGIN) for url in urls)
    assert button.is_enabled() and page.get_by_role("button").count() == 1


def test_noop_external_navigation_does_not_claim_arrival_and_manual_retry_refreshes(
    connected_delivery, browser_context
):
    page, _, refreshes, grant_urls, downloads = mount(browser_context, connected_delivery)
    # The API does not document an acknowledgment. A void/no-op host
    # therefore cannot be distinguished from an actual browser dispatch here.
    page.evaluate("()=>{window.openai.openExternal=()=>undefined;}")
    button = page.get_by_role("button", name="Download PDF")
    sync_api.expect(button).to_be_enabled()
    button.click()
    page.get_by_text("Browser download requested. Check your browser for the PDF or Save dialog.").wait_for()
    assert len(refreshes) == 1 and len(grant_urls) == 1 and not downloads
    assert len(browser_context.pages) == 1
    assert page.get_by_text("Download opened in your browser.").count() == 0
    assert button.is_enabled() and page.get_by_role("button").count() == 1
    page.evaluate("""()=>{window.openai.openExternal=({href,redirectUrl})=>{
      if(redirectUrl!==false)throw Error('Invalid navigation');
      window.open(href,'_blank','noopener');
    };}""")
    with browser_context.expect_page() as opened:
        button.click()
    wait_download(opened.value, downloads)
    assert len(refreshes) == 2 and len(downloads) == 1
    assert grant_urls[0] != grant_urls[1]


def test_double_click_is_suppressed_and_keyboard_focus_is_visible(delivery, browser_context):
    page, _, refreshes, _, downloads = mount(browser_context, delivery)
    button = page.get_by_role("button", name="Download PDF")
    sync_api.expect(button).to_be_enabled()
    page.keyboard.press("Tab")
    assert button.evaluate(
        "element => element===document.activeElement && getComputedStyle(element).outlineStyle!=='none'"
    )
    with browser_context.expect_page() as opened:
        button.evaluate("element=>{element.click();element.click();}")
    wait_download(opened.value, downloads)
    assert len(refreshes) == 1 and len(downloads) == 1
