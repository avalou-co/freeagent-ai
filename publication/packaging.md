# Hosted plugin package

The intended user journey is install, connect FreeAgent, then use the bundled
workflows. Users must not configure servers, tokens, a local runtime or an Avalou
account. The root development plugin remains a local stdio integration.

Operators build the hosted submission ZIP with:

```sh
python scripts/package_hosted_plugin.py /private/output/freeagent-ai.zip
```

Provide `FREEAGENT_PLUGIN_CLIENT_ID` through protected deployment configuration.
The package includes the public HTTPS endpoint, a pre-registered OAuth client,
both scopes, ten skills and their shared safety/API references, including the
read-only decimal mileage preview script. It excludes
application source, local launch commands, credentials, deployment runbooks and
review evidence. Output must be outside this public checkout. Never add client
secrets to the package; enter them privately in the publisher connection flow.

The generated ZIP is a packaging candidate, not proof of a working installation
or a completed submission. The publisher must register the exact callback shown
by the connection flow through deployment configuration, complete authentication,
and validate the installed package. Finish verified publisher/policy metadata,
assets, dedicated reviewer access and the actual walkthrough before submission.
Keep deployment-specific package copies and operational evidence private.

See [OpenAI packaging](https://developers.openai.com/plugins/build/plugins) and
[review cases](review-cases.md). A local marketplace or custom connection does
not satisfy public directory publication in issue #36.
