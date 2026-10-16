"""Landing page and framework-free static export.

The same assets ship in the application wheel and static exports. No network
requests or accounting clients are needed to render or preview the page.
"""

import argparse
import html
import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).with_name("landing")
LINKS = ("listing_url", "privacy_url", "terms_url", "support_url")
PROVIDERS = {"listing_url": ("chatgpt.com", "ChatGPT"), "claude_url": ("claude.ai", "Claude")}


def load_config(path: str | Path) -> dict[str, str]:
    """Require publisher approval and explicit destinations before launch."""
    return validate_config(json.loads(Path(path).read_text()))


def validate_config(config: object) -> dict[str, str]:
    """Validate non-secret launch configuration from JSON or environment."""
    if not isinstance(config, dict) or config.get("policies_approved") is not True:
        raise ValueError("Landing launch requires policies_approved=true and publisher-approved policy links")
    result = {}
    for key in (*LINKS, "claude_url"):
        value = config.get(key, "")
        if key in PROVIDERS and value == "":
            result[key] = ""
            continue
        if not isinstance(value, str) or any(char.isspace() or ord(char) < 32 for char in value):
            raise ValueError(f"Landing {key} must be an absolute HTTPS URL")
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port:
            raise ValueError(f"Landing {key} must be an absolute HTTPS URL without credentials or a port")
        if key in PROVIDERS and (parsed.hostname != PROVIDERS[key][0] or parsed.path in ("", "/")):
            raise ValueError(f"Landing {key} must be a verified listing URL on {PROVIDERS[key][0]}")
        if (
            key not in PROVIDERS
            and parsed.hostname == "freeagent-ai.avalou.co"
            and parsed.path.rstrip("/") != "/" + key.removesuffix("_url")
        ):
            raise ValueError("Local policy/support links must use their published policy routes")
        result[key] = value
    return result


def render(config: dict[str, str]) -> str:
    """Escape configured links; the source template contains no executable data."""
    document = (ROOT / "index.html").read_text()
    buttons = []
    for key, (_, name) in PROVIDERS.items():
        brand = (
            '<img src="/landing-assets/chatgpt-blossom-white.svg" width="64" height="64" alt="" /><span>ChatGPT</span>'
            if name == "ChatGPT"
            else '<img class="claude-wordmark" src="/landing-assets/claude-wordmark.svg" width="160" height="35" alt="Claude" />'
        )
        url = config.get(key, "")
        classes = f"provider-button provider-{name.lower()}"
        if url:
            button = (
                f'<a class="{classes}" href="{html.escape(url, quote=True)}" aria-label="Connect in {name}">{brand}</a>'
            )
        else:
            button = f'<button class="{classes}" type="button" disabled aria-label="{name}, connection unavailable"><span class="availability-badge">Unavailable</span>{brand}</button>'
        buttons.append(button)
    document = document.replace("{{provider_buttons}}", '<div class="provider-buttons">' + "".join(buttons) + "</div>")
    for key in LINKS:
        document = document.replace("{{" + key + "}}", html.escape(config[key], quote=True))
    return document


def build(output: Path, config: dict[str, str]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "assets", output / "landing-assets", dirs_exist_ok=True)
    (output / "index.html").write_text(render(config))


SITE_NOTICES = {
    "privacy": (
        "Privacy",
        [
            "Avalou operates FreeAgent AI. For privacy questions or requests about your personal information, contact hello@avalou.co.",
            "This notice covers the website and connected FreeAgent AI service. Browsing the website does not give Avalou access to your FreeAgent account. Connected access requires separate application sign-in and FreeAgent authorization.",
            "We serve fonts, images and scripts from this site. We do not include analytics, advertising trackers or a contact form. Your browser can store your light/dark theme choice in local storage; you can remove it through your browser settings.",
            "Google Firebase Hosting delivers this website and processes technical network information, including IP addresses, to serve and secure requests. If you email us, we receive the information you include to answer your enquiry.",
            "We use technical information to operate and secure the website, and enquiry information to respond to you. Our lawful basis is our legitimate interest in providing a secure website and answering enquiries. We retain enquiry information while resolving your request and any related dispute; hosting providers retain technical records under their service policies.",
            "When you connect, Auth0 processes application sign-in and FreeAgent processes company authorization. Google Cloud hosts the application and stores the Auth0 user identifier, linked company identifier, encrypted FreeAgent access and refresh tokens, and connection versions and revocation timestamps. Encryption keys are held separately in Google Secret Manager. Temporary login state, browser sessions and request-rate counters expire; expired state cannot be used while awaiting storage cleanup.",
            "When you ask your assistant to read or change accounting records, FreeAgent AI sends the request to your linked FreeAgent company and returns the result to the assistant. Results can contain personal and financial information about you, your contacts and your business. ChatGPT/OpenAI and other assistants process results under their own terms and privacy notices. Only connect information you are permitted to share. Review and approve accounting changes before they are sent.",
            "We use connected-service information to provide the connection and operations you request and to protect account access. Credentials remain stored while the connection is active. Disconnecting deletes the stored encrypted credentials and retains a user identifier, connection version and cutoff timestamp to prevent old authorizations from regaining access. These security markers have no automatic expiry; contact hello@avalou.co about deletion. Temporary state is deleted through expiry-based cleanup. Optional connection-database backups are currently disabled.",
            "Disconnecting FreeAgent AI does not delete accounting records in FreeAgent, previous results in your assistant, or the Auth0 sign-in account. Manage those records through each provider and remove the assistant connection separately. Google, Auth0, FreeAgent and your assistant provider may process technical information under their service policies, including outside your country. Contact us for information about service providers, retention and applicable transfer arrangements.",
            "Depending on the circumstances, you can request access, correction, deletion, restriction or portability of your personal information, or object to its use. Contact hello@avalou.co to make a request. You can also complain to the UK Information Commissioner's Office at ico.org.uk.",
        ],
    ),
    "terms": (
        "Terms",
        [
            "Avalou provides FreeAgent AI to help you work with your UK FreeAgent account through an AI assistant. Contact hello@avalou.co with questions about these terms.",
            "Use FreeAgent AI only with accounts and information you have permission to access. Keep your sign-in credentials secure and review the permissions you grant when connecting a service.",
            "Review proposed accounting changes before approving them and check the results in FreeAgent. You remain responsible for your accounting records, submissions and business decisions. AI output can contain mistakes and is not professional accounting, tax or legal advice.",
            "Features depend on the connected provider, your account permissions and service availability. We may change or suspend features to maintain the service or address security issues. These terms do not limit rights you have under applicable law.",
            "FreeAgent, ChatGPT, OpenAI and Claude are third-party products and trademarks of their respective owners. Their own terms and privacy policies apply when you use their services. Avalou does not claim their endorsement.",
        ],
    ),
    "support": (
        "Support",
        [
            "For FreeAgent AI help, product questions or feedback, email hello@avalou.co.",
            "Include the assistant you use, what you were trying to do, and any error message. Remove personal or financial information from screenshots before sending them.",
            "Do not include passwords, OAuth secrets, access tokens, bank details or accounting documents in support email.",
        ],
    ),
}


def build_static(output: Path) -> None:
    """Export a public marketing site, without enabling the connected service."""
    config = {key: "" for key in PROVIDERS}
    config.update({key + "_url": "/" + key + "/" for key in SITE_NOTICES})
    build(output, config)
    for metadata in (output / "landing-assets").rglob("*.json"):
        metadata.unlink()
    index = output / "index.html"
    index.write_text(
        index.read_text()
        .replace('href="/account"', 'href="#connection"')
        .replace("Manage connection", "How to connect")
    )
    for slug, (title, paragraphs) in SITE_NOTICES.items():
        directory = output / slug
        directory.mkdir(exist_ok=True)
        body = "".join("<p>" + html.escape(paragraph) + "</p>" for paragraph in paragraphs)
        document = (
            '<!doctype html><html lang="en-GB"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<link rel="stylesheet" href="/landing-assets/site.css?v=4">'
            "<title>" + html.escape(title) + " | FreeAgent AI | Avalou</title></head>"
            '<body><main class="notice"><a href="/">FreeAgent AI by Avalou</a><h1>'
            + html.escape(title)
            + "</h1>"
            + body
            + "</main></body></html>"
        )
        (directory / "index.html").write_text(document)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="Publisher-approved launch JSON")
    parser.add_argument(
        "--static",
        action="store_true",
        help="Public marketing export with local website notices and disabled connections",
    )
    parser.add_argument("--preview", action="store_true", help="Local design preview only; never deploy this output")
    parser.add_argument("--output", type=Path, default=Path("build/landing"))
    args = parser.parse_args()
    if sum((bool(args.config), args.preview, args.static)) != 1:
        parser.error("Choose exactly one of --config, --preview or --static")
    if args.static:
        build_static(args.output)
        return
    config: dict[str, str] = (
        {key: "" if key in PROVIDERS else "#connection" for key in LINKS} if args.preview else load_config(args.config)
    )
    build(args.output, config)


if __name__ == "__main__":
    main()
