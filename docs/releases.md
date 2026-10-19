# Releases

`pyproject.toml` owns the release version. Keep `.claude-plugin/plugin.json` and
`.codex-plugin/plugin.json` at that version; the hosted ZIP builder reads it from
`pyproject.toml`. Keep `VERSION` in `freeagent_ai/public_package.py` at that
version too; CI checks the output of both package builders. The marketplace file
has no separate version. CI checks both local manifests, both generated plugin
manifests, the hosted MCP server version, the hosted HTTP User-Agent and a matching
changelog heading against `pyproject.toml` on Python 3.10, 3.12 and 3.13. The
runtime checks inspect Python syntax without starting the hosted service or
using deployment credentials. Any mismatch fails the existing pytest CI job.

## Prepare a release

1. Read the latest `origin/main`, existing tags and GitHub Releases before choosing
   a version. Never reuse a published version or replace a release tag.
2. Update those version fields, the hosted server version in
   `freeagent_ai/hosted_app.py`, the User-Agent in `freeagent_ai/hosted_client.py`
   and `CHANGELOG.md` in a PR. Version 0.3.0 is
   the first planned tagged release; its notes include the initial hosted work.
   Preserve the 0.3.0 version introduced by the hosted marketplace packaging
   work; it supersedes the older 0.2.0 release target in issue #33. Rebuild
   submission ZIPs from the exact release commit.
3. Install development dependencies and run the same checks as CI:

   ```bash
   python -m pip install -e ".[hosted,dev]"
   ruff check .
   ruff format --check .
   pyright
   pytest
   node --test auth0/primary-auth-time.test.js
   ```

4. Review the diff and release notes, then have the owner review and merge the
   PR. Confirm CI passes on the exact merged commit before tagging. A local test
   pass does not establish CI or production readiness.

## Tag and publish

The publishing owner performs these steps from a clean checkout of merged
`main`. Check the configured remote is `avalou-co/freeagent-ai` and that no
`v0.3.0` tag or Release exists locally or remotely. Stop if it already exists.

```bash
git fetch origin main --tags
git switch main
git pull --ff-only origin main
git status --short
git rev-parse HEAD origin/main
gh run list --commit "$(git rev-parse HEAD)"
git tag --list v0.3.0
git ls-remote --tags origin refs/tags/v0.3.0
gh release list --repo avalou-co/freeagent-ai
```

Continue only when the checkout is clean, both commit IDs match, the relevant
CI checks succeeded and the version is unused. Copy only the 0.3.0 entry from
`CHANGELOG.md` into a release-notes file outside the checkout, then create and
verify the annotated tag:

```bash
git tag -a v0.3.0 -m "chore: release v0.3.0"
git push origin refs/tags/v0.3.0
gh release create v0.3.0 --repo avalou-co/freeagent-ai --verify-tag \
  --title "v0.3.0" --notes-file /tmp/freeagent-ai-v0.3.0-notes.md
git ls-remote --tags origin 'refs/tags/v0.3.0*'
gh release view v0.3.0 --repo avalou-co/freeagent-ai
```

Compare the remote peeled tag commit (`refs/tags/v0.3.0^{}`) with the verified
merged commit. If publication fails after pushing, inspect the tag and Release
before retrying; retain the existing tag and finish only the missing step.

This process publishes a GitHub source release. It does not publish to PyPI,
submit or publish a directory listing, or prove hosted account journeys work.
Build any hosted submission ZIP separately from that exact release checkout
using [the hosted plugin packaging instructions](../publication/packaging.md).
Keep deployment inputs, reviewer credentials,
operator evidence and deployment-specific ZIPs outside this public repository
and its Release assets. Record the public Release URL in the GitHub issue after
verification; keep the release issue open until the tag and Release exist.
