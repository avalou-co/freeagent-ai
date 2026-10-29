"""Publish only a static artifact using the application's routing configuration."""

import argparse
import gzip
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from freeagent_ai.workflow_pages import WORKFLOWS

API = "https://firebasehosting.googleapis.com/v1beta1/"


def resource_name(value, kind, *, project, site):
    """Accept Firebase's two names for the configured deployment site."""
    if not re.fullmatch(r"[a-z][a-z0-9-]+", project) or not re.fullmatch(r"[a-z0-9-]+", site):
        raise ValueError("Invalid Hosting project or site")
    resource = "sites/" + site
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:projects/" + re.escape(project) + r"/)?" + re.escape(resource) + "/" + kind + r"/[A-Za-z0-9_-]+", value
    ):
        raise ValueError("Unexpected Hosting " + kind + " resource")
    return value.removeprefix("projects/" + project + "/")


def manifest(root):
    files, blobs = {}, {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Static exports cannot contain symbolic links")
        if not path.is_file():
            continue
        name = "/" + path.relative_to(root).as_posix()
        allowed = (
            name
            in {
                "/index.html",
                "/privacy/index.html",
                "/terms/index.html",
                "/support/index.html",
                "/robots.txt",
                "/sitemap.xml",
            }
            or name in {f"/workflows/{slug}/index.html" for slug in WORKFLOWS}
            or name.startswith("/landing-assets/")
        )
        if not allowed or path.suffix not in {
            ".html",
            ".css",
            ".js",
            ".svg",
            ".woff2",
            ".webp",
            ".png",
            ".txt",
            ".xml",
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


def deployment_config(config, *, service, region):
    if not re.fullmatch(r"[a-z][a-z0-9-]+", service) or not re.fullmatch(r"[a-z]+-[a-z]+[0-9]+", region):
        raise ValueError("Invalid Hosting backend service or region")
    return {**config, "rewrites": [{"glob": "**", "run": {"serviceId": service, "region": region}}]}


def publish(root, config, *, project, site):
    def name(value, kind):
        return resource_name(value, kind, project=project, site=site)

    target = "projects/" + project + "/sites/" + site
    name("sites/" + site + "/versions/preflight", "versions")
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
            raise RuntimeError(f"Hosting {method} failed: HTTP {error.code}") from None

    version = name(request("POST", API + target + "/versions", {"config": config})["name"], "versions")
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
        API + target + "/releases?" + urlencode({"versionName": version}),
        {"message": "Application website publication"},
    )
    # Read back the exact release without allowing authenticated redirects.
    release_name = name(release["name"], "releases")
    readback = request("GET", API + release_name)
    if name(readback.get("version", {}).get("name"), "versions") != version:
        raise RuntimeError("Released version did not match the static export")
    print("Published and verified website release")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    try:
        config = deployment_config(
            json.loads(args.config.read_text()),
            service=os.environ["HOSTING_BACKEND_SERVICE"],
            region=os.environ["HOSTING_BACKEND_REGION"],
        )
        publish(args.root, config, project=os.environ["GOOGLE_CLOUD_PROJECT"], site=os.environ["FIREBASE_HOSTING_SITE"])
    except KeyError:
        raise SystemExit("Hosting deployment configuration incomplete") from None
