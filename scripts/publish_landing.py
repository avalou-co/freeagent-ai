"""Publish only a static artifact using the application's routing configuration."""

import argparse
import gzip
import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

API = "https://firebasehosting.googleapis.com/v1beta1/"
SITE = "projects/avalou-prod/sites/avalou-freeagent-ai"
RESOURCE = "sites/avalou-freeagent-ai"


def manifest(root):
    files, blobs = {}, {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Static exports cannot contain symbolic links")
        if not path.is_file():
            continue
        name = "/" + path.relative_to(root).as_posix()
        allowed = name in {
            "/index.html",
            "/privacy/index.html",
            "/terms/index.html",
            "/support/index.html",
        } or name.startswith("/landing-assets/")
        if not allowed or path.suffix not in {
            ".html",
            ".css",
            ".js",
            ".svg",
            ".woff2",
            ".webp",
            ".txt",
        }:
            raise ValueError("Unexpected static export file: " + name)
        data = gzip.compress(path.read_bytes(), mtime=0)
        digest = hashlib.sha256(data).hexdigest()
        files[name] = digest
        blobs[digest] = data
    required = {
        "/index.html",
        "/privacy/index.html",
        "/terms/index.html",
        "/support/index.html",
    }
    if not required.issubset(files):
        raise ValueError("Static export is missing its root or website notices")
    return files, blobs


def publish(root, config):
    files, blobs = manifest(root)
    token = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()

    def request(method, url, body=None):
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname
            not in {
                "firebasehosting.googleapis.com",
                "upload-firebasehosting.googleapis.com",
            }
            or parsed.port
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Unexpected Hosting API destination")
        binary = isinstance(body, bytes)
        payload = body if binary else json.dumps(body).encode() if body is not None else None
        req = Request(
            url,
            data=payload,
            method=method,
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/octet-stream" if binary else "application/json",
            },
        )

        # No redirects: never forward Google credentials to a redirected target.
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        try:
            with build_opener(NoRedirect).open(req, timeout=30) as response:
                data = response.read()
                return json.loads(data) if data and not binary else {}
        except HTTPError as error:
            raise RuntimeError(f"Hosting {method} {parsed.path} failed: HTTP {error.code}") from None

    version = request("POST", API + SITE + "/versions", {"config": config})["name"]
    if not re.fullmatch(re.escape(RESOURCE) + r"/versions/[A-Za-z0-9_-]+", version):
        raise ValueError("Unexpected Hosting version resource")
    populated = request("POST", API + version + ":populateFiles", {"files": files})
    for digest in populated.get("uploadRequiredHashes", []):
        if digest not in blobs:
            raise ValueError("Hosting requested an unknown content hash")
        request("POST", populated["uploadUrl"] + "/" + digest, blobs[digest])
    finalized = request("PATCH", API + version + "?updateMask=status", {"status": "FINALIZED"})
    if finalized.get("status") != "FINALIZED":
        raise RuntimeError("Hosting version was not finalized")
    release = request(
        "POST",
        API + SITE + "/releases?" + urlencode({"versionName": version}),
        {"message": "Public landing; accounting backend remains private"},
    )
    name = release["name"]
    # Read back the exact release without allowing authenticated redirects.
    if not re.fullmatch(re.escape(RESOURCE) + r"/releases/[A-Za-z0-9_-]+", name):
        raise ValueError("Unexpected Hosting release resource")
    readback = request("GET", API + name)
    if readback.get("version", {}).get("name") != version:
        raise RuntimeError("Released version did not match the static export")
    print("Published and verified " + version)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    publish(args.root, json.loads(args.config.read_text()))
