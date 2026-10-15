"""Launch-gated landing page and framework-free static export.

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
        if key not in PROVIDERS and parsed.hostname == "freeagent-ai.avalou.co":
            raise ValueError(
                "Policy/support links must use approved external pages; local routes are setup placeholders"
            )
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
            button = f'<button class="{classes}" type="button" disabled aria-label="{name}, coming soon"><span class="availability-badge">Coming soon</span>{brand}</button>'
        buttons.append(button)
    document = document.replace("{{provider_buttons}}", '<div class="provider-buttons">' + "".join(buttons) + "</div>")
    for key in LINKS:
        document = document.replace("{{" + key + "}}", html.escape(config[key], quote=True))
    return document


def build(output: Path, config: dict[str, str]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "assets", output / "landing-assets", dirs_exist_ok=True)
    (output / "index.html").write_text(render(config))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="Publisher-approved launch JSON")
    parser.add_argument("--preview", action="store_true", help="Local design preview only; never deploy this output")
    parser.add_argument("--output", type=Path, default=Path("build/landing"))
    args = parser.parse_args()
    if bool(args.config) == args.preview:
        parser.error("Choose exactly one of --config or --preview")
    config: dict[str, str] = (
        {key: "" if key in PROVIDERS else "#connection" for key in LINKS} if args.preview else load_config(args.config)
    )
    build(args.output, config)


if __name__ == "__main__":
    main()
