"""Build an allowlisted hosted plugin ZIP; deployment inputs stay outside source."""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Support the documented source-checkout invocation as well as an installed package.
sys.path.insert(0, str(ROOT))

from freeagent_ai.public_package import package_files, write_archive  # noqa: E402


def build(output: Path, client_id: str) -> None:
    """Build a private operator candidate; publication approval remains a separate gate."""
    if not client_id.strip():
        raise ValueError("Set FREEAGENT_PLUGIN_CLIENT_ID to the registered OAuth client ID")
    entries = package_files(ROOT, {"mcp_client_id": client_id})
    entries["CANDIDATE-NOT-FOR-SUBMISSION.txt"] = (
        b"Private operator candidate only. Installed web/mobile document delivery acceptance and publication approvals remain separate.\n"
    )
    # Never replace an artifact, and keep operator-supplied metadata private on disk.
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        write_archive(stream, entries)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New ZIP path outside the public checkout")
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(ROOT):
        parser.error("Write the deployment-specific package outside the public checkout")
    build(args.output, os.environ.get("FREEAGENT_PLUGIN_CLIENT_ID", ""))
