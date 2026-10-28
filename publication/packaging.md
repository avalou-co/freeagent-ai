# Hosted plugin package

The intended user journey is install, connect FreeAgent, then use the bundled
workflows. Users must not configure servers, tokens, a local runtime or an Avalou
account. The root development plugin remains a local stdio integration.

Install the package with its hosted dependencies (`pip install -e ".[hosted]"`).
Operators build the hosted submission ZIP with:

```sh
python scripts/package_hosted_plugin.py /private/output/freeagent-ai.zip
```

Provide `FREEAGENT_PLUGIN_CLIENT_ID` through protected deployment configuration.
The package includes the public HTTPS endpoint, a pre-registered OAuth client,
both scopes, all canonical skills and their shared safety/API references. No
client-executable scripts or custom accounting calculators are bundled. The operator command and
`python -m freeagent_ai.public_package` share manifest construction, named-tool
workflow rendering, tool-reference checks and deterministic ZIP writing. The candidate includes the public tool audit and source digests.
It excludes application source, local launch commands, credentials, deployment
runbooks and private review evidence. The operator command preserves mode 0600
and refuses replacement; the public release builder separately requires publication
evidence and assets. A candidate does not assert those release approvals. Output
must be outside this public checkout. Never add client secrets to the package;
enter them privately in the publisher connection flow.

The generated ZIP is a packaging candidate, not proof of a working installation
or a completed submission. The publisher must register the exact callback shown
by the connection flow through deployment configuration, complete authentication,
and validate the installed package. Finish verified publisher/policy metadata,
assets, dedicated reviewer access and the actual walkthrough before submission.
Keep deployment-specific package copies and operational evidence private.

See [OpenAI packaging](https://developers.openai.com/plugins/build/plugins) and
[review cases](review-cases.md). A local marketplace or custom connection does
not satisfy public directory publication in issue #36.

## Backend delivery

Merging application code runs CI. Successful main-branch push CI triggers
`Build hosted image`, which checks out that exact tested commit and publishes an
immutable digest handoff. `Promote backend` then requests deployment through the
protected deployment workflow. Website publication is separate and is not proof
that the backend changed. Pull requests and failed tests cannot promote images.

The production environment must supply `BACKEND_PROMOTION_APP_ID`,
`BACKEND_PROMOTION_APP_PRIVATE_KEY` and
`BACKEND_DEPLOYMENT_REPOSITORY_NAME` through protected configuration. The GitHub
App installation is restricted to the deployment repository and Actions write;
it dispatches the deployment workflow without repository contents write or cloud
apply permissions. Never put private destinations or credentials in this public
repository. A successful image build alone is not deployment success; inspect the
private apply and running-revision verification.
