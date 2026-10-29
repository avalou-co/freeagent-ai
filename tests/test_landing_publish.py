import gzip
import hashlib
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "publish_landing", Path(__file__).parents[1] / "scripts/publish_landing.py"
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def seed(root):
    for name in (
        "index.html",
        "privacy/index.html",
        "terms/index.html",
        "support/index.html",
    ):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("A public website page")


def test_static_upload_hashes_match_the_actual_gzip_content(tmp_path):
    seed(tmp_path)
    files, blobs = module.manifest(tmp_path)
    assert len(files) == 4
    assert all(gzip.decompress(blobs[digest]) == b"A public website page" for digest in files.values())
    assert all(hashlib.sha256(data).hexdigest() == digest for digest, data in blobs.items())


def test_credentials_and_symlinks_are_not_static_content(tmp_path):
    seed(tmp_path)
    (tmp_path / "credentials.json").write_text("private fixture")
    with pytest.raises(ValueError, match="Unexpected static export"):
        module.manifest(tmp_path)
    (tmp_path / "credentials.json").unlink()
    (tmp_path / "linked.html").symlink_to(tmp_path / "index.html")
    with pytest.raises(ValueError, match="symbolic links"):
        module.manifest(tmp_path)


@pytest.mark.parametrize("prefix", ["", "projects/example-project/"])
@pytest.mark.parametrize("mismatch", [False, True])
def test_publish_uses_canonical_resource_names_and_verifies_release(tmp_path, monkeypatch, mismatch, prefix):
    import io
    import json

    seed(tmp_path)
    version = "sites/example-site/versions/abc123"
    release = "sites/example-site/releases/123456"
    responses = [
        {"name": prefix + version},
        {"uploadRequiredHashes": []},
        {"status": "FINALIZED"},
        {"name": prefix + release},
        {"version": {"name": prefix + version + "wrong" if mismatch else prefix + version}},
    ]
    calls = []

    class Opener:
        def open(self, request, timeout):
            calls.append((request.method, request.full_url))
            return io.BytesIO(json.dumps(responses.pop(0)).encode())

    monkeypatch.setattr(module, "build_opener", lambda *args: Opener())
    monkeypatch.setattr(module.subprocess, "check_output", lambda *a, **kw: "test-token")
    if mismatch:
        with pytest.raises(RuntimeError, match="did not match"):
            module.publish(tmp_path, {}, project="example-project", site="example-site")
    else:
        module.publish(tmp_path, {}, project="example-project", site="example-site")
    assert calls[1] == ("POST", module.API + version + ":populateFiles")
    assert calls[-1] == ("GET", module.API + release)
    assert not responses


@pytest.mark.parametrize(
    "name",
    [
        "projects/another-project/sites/example-site/versions/123",
        "projects/example-project/sites/another-site/versions/123",
        "sites/example-site/releases/123",
        "sites/example-site/versions/../123",
        "sites/example-site/versions/123?redirect=elsewhere",
        None,
    ],
)
def test_version_names_cannot_change_project_site_or_resource(name):
    with pytest.raises(ValueError, match="Unexpected Hosting"):
        module.resource_name(name, "versions", project="example-project", site="example-site")


def test_backend_config_uses_only_explicit_deployment_inputs():
    result = module.deployment_config({"headers": []}, service="example-service", region="europe-west1")
    assert result["rewrites"] == [{"glob": "**", "run": {"serviceId": "example-service", "region": "europe-west1"}}]
    for service, region in [("../other", "europe-west1"), ("example-service", "bad/region")]:
        with pytest.raises(ValueError):
            module.deployment_config({}, service=service, region=region)


def test_real_export_can_publish_versioned_assets_and_png(tmp_path):
    import json

    from freeagent_ai.landing import ASSET_PREFIX, build_static

    build_static(tmp_path)
    files, _ = module.manifest(tmp_path)
    assert ASSET_PREFIX + "social-card-v1.png" in files
    assert ASSET_PREFIX + "site.css" in files
    assert ASSET_PREFIX + "fonts/hanken-grotesk-latin.woff2" in files
    homepage = (tmp_path / "index.html").read_text()
    assert ASSET_PREFIX + "site.css" in homepage
    assert ASSET_PREFIX + "site.js" in homepage
    assert ASSET_PREFIX + "site.css" in (tmp_path / "support/index.html").read_text()
    config = json.loads((Path(__file__).parents[1] / "hosting.json").read_text())
    rules = {rule["glob"]: rule["headers"] for rule in config["headers"]}
    assert rules["**"]["Cache-Control"] == "no-store"
    assert rules["/landing-assets/v-*/**"]["Cache-Control"] == "public, max-age=31536000, immutable"
    assert rules["/{,index.html}"]["Cache-Control"] == "public, max-age=0, must-revalidate"


def test_asset_namespace_changes_when_asset_bytes_change(tmp_path, monkeypatch):
    from freeagent_ai import landing

    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "site.css").write_text("first")
    monkeypatch.setattr(landing, "ROOT", tmp_path)
    before = landing.asset_version()
    assert landing.asset_version() == before
    (assets / "site.css").write_text("second")
    assert landing.asset_version() != before
