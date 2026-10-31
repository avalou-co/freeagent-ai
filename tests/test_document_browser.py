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
    assert len(refreshes) == 1 and len(downloads) == 1
    directory = os.environ.get("FREEAGENT_UX_SCREENSHOT_DIR")
    if directory and not elapsed:
        name = "mobile" if receiver.viewport_size["width"] == 390 else "desktop"
        receiver.screenshot(path=str(Path(directory) / (name + "-ready.png")), full_page=True)
    assert receiver.get_by_role("button").count() == 0
    assert receiver.get_by_role("link", name="Download PDF").is_visible()
    assert receiver.get_by_role("heading", name="Your PDF is ready").is_visible()
    assert receiver.url == ORIGIN + "/documents"
    assert receiver.locator("#grant").count() == 0
    assert all("#" not in url and "grant=" not in url and "/login" not in url for url in urls)
    assert receiver.evaluate("Object.keys(localStorage).length+Object.keys(sessionStorage).length") == 0
    replay = browser_context.new_page()
    replay.goto(grant_urls[0])
    replay.get_by_role("heading", name="Your PDF isn’t available").wait_for()
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
    page.get_by_text("Couldn’t open this PDF. Select the document again, or check the connected account.").wait_for()
    assert len(refreshes) == 1 and not downloads
    assert not any(url.startswith(ORIGIN) for url in urls)
    assert button.is_enabled()
    assert page.get_by_role("heading", name="Invoice INV-007").is_visible()


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


def open_receiver(page, browser_context):
    with browser_context.expect_page() as opened:
        page.get_by_role("button", name="Download PDF").click()
    return opened.value


def test_browser_preparation_is_visible_and_manual_ready_download_reuses_received_bytes(delivery, browser_context):
    d = delivery
    page, _, refreshes, _, downloads = mount(browser_context, d)
    pending = []

    def hold(route):
        response = d.download(route.request.post_data.split("=", 1)[1])
        pending.append((route, response))

    browser_context.route(ORIGIN + "/documents/download", hold)
    before = len(d.calls)
    receiver = open_receiver(page, browser_context)
    receiver.get_by_role("heading", name="Preparing your PDF").wait_for()
    sync_api.expect(receiver.locator("#download")).to_be_hidden()
    assert receiver.locator(".activity span").first.evaluate("e=>getComputedStyle(e).animationName") == "breathe"
    receiver.emulate_media(reduced_motion="reduce")
    assert receiver.locator(".activity span").first.evaluate("e=>getComputedStyle(e).animationName") == "none"
    directory = os.environ.get("FREEAGENT_UX_SCREENSHOT_DIR")
    if directory:
        name = "mobile" if receiver.viewport_size["width"] == 390 else "desktop"
        receiver.screenshot(path=str(Path(directory) / (name + "-preparing.png")), full_page=True)
    receiver.wait_for_function("document.querySelector('main').dataset.state==='preparing'")
    assert len(pending) == 1
    route, response = pending[0]
    route.fulfill(status=response.status_code, headers=dict(response.headers), body=response.content)
    wait_download(receiver, downloads)
    assert len(d.calls) - before == 2  # No PDF read during widget authorization.
    ready = receiver.get_by_role("link", name="Download PDF")
    assert ready.is_visible()
    calls = len(d.calls)
    downloads[0].cancel()  # No completion acknowledgment changes the ready screen.
    with receiver.expect_download() as repeated:
        ready.click()
    assert repeated.value.suggested_filename == "invoices-7.pdf"
    assert len(pending) == 1 and len(refreshes) == 1 and len(d.calls) == calls
    assert receiver.get_by_role("heading", name="Your PDF is ready").is_visible()
    receiver.evaluate(
        "window.dispatchEvent(new PageTransitionEvent('pagehide'));window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}))"
    )
    assert ready.is_hidden()
    assert receiver.get_by_role("heading", name="Your PDF isn’t available").is_visible()


def test_blocked_automatic_download_keeps_ready_button_for_explicit_user_action(delivery, browser_context):
    browser_context.add_init_script("HTMLAnchorElement.prototype.click=function(){};")
    page, _, _, _, downloads = mount(browser_context, delivery)
    receiver = open_receiver(page, browser_context)
    receiver.get_by_role("heading", name="Your PDF is ready").wait_for()
    assert not downloads
    with receiver.expect_download() as opened:
        receiver.get_by_role("link", name="Download PDF").click()
    assert opened.value.suggested_filename == "invoices-7.pdf"


@pytest.mark.parametrize("failure", ["wrong_mime", "oversized", "wrong_filename", "http_error", "timeout"])
def test_browser_preparation_failure_stays_actionable_without_replaying(delivery, browser_context, failure):
    page, _, _, _, downloads = mount(browser_context, delivery)
    requests, held = [], []
    if failure == "timeout":
        browser_context.add_init_script(
            "const nativeTimeout=window.setTimeout;window.setTimeout=(fn,ms,...args)=>nativeTimeout(fn,ms===45000?50:ms,...args);"
        )

    def respond(route):
        requests.append(route.request)
        headers = {"Content-Type": "application/pdf", "Content-Disposition": 'attachment; filename="invoices-7.pdf"'}
        if failure == "timeout":
            held.append(route)
            return
        if failure == "wrong_mime":
            headers["Content-Type"] = "text/html"
        if failure == "oversized":
            headers["Content-Length"] = str(6 * 1024 * 1024)
        if failure == "wrong_filename":
            headers["Content-Disposition"] = 'attachment; filename="../../unsafe.pdf"'
        route.fulfill(status=400 if failure == "http_error" else 200, headers=headers, body=PDF)

    browser_context.route(ORIGIN + "/documents/download", respond)
    receiver = open_receiver(page, browser_context)
    receiver.get_by_role("heading", name="Your PDF isn’t available").wait_for()
    assert receiver.get_by_text("Return to your chat and select Download PDF to try again.").is_visible()
    assert receiver.locator("#download").is_hidden()
    assert len(requests) == 1 and not downloads
    if held:
        held[0].fulfill(status=200, content_type="application/pdf", body=PDF)
        assert receiver.get_by_role("heading", name="Your PDF isn’t available").is_visible()


def test_outdated_card_guidance_requests_fresh_selection_without_navigation(delivery, browser_context):
    page, urls, _, grants, downloads = mount(browser_context, delivery)
    for (collection, key), record in list(delivery.accounts.store.records.items()):
        if record.get("kind") == "document_context":
            delivery.accounts.store.mutate(
                collection, key, lambda old: {k: v for k, v in old.items() if k != "metadata"}
            )
    before = len(delivery.calls)
    page.get_by_role("button", name="Download PDF").click()
    page.get_by_text("Couldn’t open this PDF. Select the document again, or check the connected account.").wait_for()
    assert len(delivery.calls) == before and not grants and not downloads
    assert not any(url.startswith(ORIGIN) for url in urls)
