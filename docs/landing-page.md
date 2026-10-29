# FreeAgent AI landing page

The launch page lives in `freeagent-ai`, alongside the service it describes.
The public site uses Avalou branding. Private deployment configuration owns
cloud resources, DNS and backend routing. No new frontend framework or deployment system is
needed. The existing Firebase catch-all forwards `/`, `/landing-assets/*`, MCP,
account routes and discovery to Cloud Run. The app serves only the marketing root
and its own asset prefix; it does not add an SPA fallback or intercept auth routes.

## Local preview

From an environment with the project's dependencies installed:

```sh
python -m freeagent_ai.landing --preview
python -m http.server 8765 --directory build/landing
```

Open `http://localhost:8765`. This is a design preview: provider buttons are
disabled and policy links point to the on-page connection explanation. `/account` requires the hosted application
and is not served by the static preview. Never deploy preview output.

The page has ChatGPT and Claude logo buttons. Each shows “Coming soon” and
remains disabled until its verified destination is configured. The workflow
sections are selected examples rather than an exhaustive feature list. Keep
this framing as capabilities grow; do not publish a fixed workflow count. They contain no
customer data or fabricated screenshots. Marketing content remains readable
without JavaScript. Screenshots/video from real ChatGPT journeys
should only be added after deployed testing produces verified evidence.

## Launch configuration

Leave `FREEAGENT_LANDING_CONFIG` unset until the publisher has approved privacy,
terms and support pages. The application
then retains its existing pre-launch home/policy responses. Shipping these source
files alone does not enable the marketing page.

To enable the page, supply a JSON object as the non-secret environment variable
`FREEAGENT_LANDING_CONFIG` through reviewed private deployment configuration:

- `listing_url`: optional verified listing URL on `https://chatgpt.com`. Omit it
  or set it to an empty string to leave ChatGPT disabled.
- `claude_url`: optional verified connection URL on `https://claude.ai`. Omit it
  or set it to an empty string to leave Claude disabled.

- `privacy_url`, `terms_url`, `support_url`: approved, publicly accessible HTTPS
  pages hosted outside `freeagent-ai.avalou.co`. Local policy routes currently
  contain setup-pending content and are deliberately rejected as launch targets.
- `policies_approved`: the JSON boolean `true`, set only after publisher approval.

Each provider can be enabled independently. Preview output leaves both disabled.
Provider controls appear only in the hero, with no repeated closing CTA. On mobile, each
workflow heading and description precedes its illustration. The illustrations
use compact document labels while the main descriptions retain readable body type.

Do not guess destinations or use example URLs in production. The validator checks
URL structure, not whether a listing is approved or a policy is legally sufficient.
Those checks remain part of the publisher's launch review. Malformed or incomplete
configuration fails startup; unset configuration preserves the existing service.
Set it only after checking every destination. `/privacy`, `/terms` and `/support`
redirect to these approved destinations once enabled.

The same JSON may be saved outside version control and used to export a standalone
static artifact:

```sh
python -m freeagent_ai.landing --config /path/to/approved-launch.json --output build/landing
```

The static export is optional. The existing Docker build packages the HTML, CSS,
JavaScript, fonts and licences in the wheel automatically. Firebase currently
serves this through the existing Cloud Run rewrite. Do not introduce a second
Firebase release owner with `firebase deploy`: Terraform already owns its version
and release. Direct static hosting would require a coordinated infrastructure
change to that existing ownership model.

## Search indexing

The static export ships `/robots.txt` and `/sitemap.xml`; Firebase Hosting serves
them before the Cloud Run rewrite. Robots allows the marketing page and blocks
account, auth and MCP routes. The sitemap lists `/` and the policy pages. Submit
the sitemap in Google Search Console after deploying.

## Security and verification

Marketing responses allow same-origin styles, scripts, images and fonts through a
restricted CSP. No inline script, external font request, analytics, account request
or accounting write is introduced. Auth/account/MCP routes retain the original
restrictive CSP; all responses retain `Cache-Control: no-store`.

Run `ruff check .`, `ruff format --check .`, `pyright`, `pytest` and
`node --check freeagent_ai/landing/assets/site.js`. Review desktop/mobile and both
themes, keyboard navigation, visible focus, disabled provider buttons and the
no-JavaScript rendering. Build a wheel and verify it contains landing assets.

Deploy only from reviewed, merged-main CI using the existing image/Terraform
handoff. Before launch verify HTTPS and real CTA/policy links, then regression-check
`/mcp` (including its unauthenticated challenge), `/account`, `/login`, both
callbacks, `/link`, `/disconnect`, `/health` and both OAuth discovery routes.
Verify auth/account responses remain no-store. Live account and directory journeys
remain a release gate; local HTTP tests do not prove them.

## Design provenance

Visual references are managed separately by the publisher.
The page uses the public forest/off-white palette, typography, provider
logo buttons, Avalou monogram, stroked SVG style, section borders and theme tokens.
It uses a product-focused header rather than duplicating consultancy navigation.

The monochrome ChatGPT/OpenAI blossom is the unmodified white SVG from
`https://cdn.openai.com/brand/openai-logos.zip`, linked by
[OpenAI's brand guidelines](https://openai.com/brand/). It identifies the ChatGPT
connection on the logo buttons, following the user's Canva reference. The ChatGPT
label is live text. Claude uses the original inline wordmark SVG from the header
of `https://claude.com/`, saved as `claude-wordmark.svg`. OpenAI retains
ownership of its trademarks; attribution and the independent-product disclaimer
appear in the footer.

The Hanken Grotesk, Libre Caslon Text and JetBrains Mono WOFF2 files are copied
unchanged from that repository's `app/fonts`. Their upstream SIL Open Font
Licences are included under `freeagent_ai/landing/assets/licenses` and ship with
both wheels and static exports.

The hero uses an original AI-generated studio photograph as decorative marketing
imagery. It carries no visible caption or product overlays. Its exact generation prompt is retained in the shipped WebP provenance sidecar.
It is not a customer testimonial or a product screenshot. Workflow artefacts and
the chart are HTML/CSS illustrations labelled as examples; they contain no real
account data. The neutral split photo hero and alternating workflow demonstrations follow
the owner’s request for a more visual Canva-like composition while retaining
Avalou’s typography and palette.

Content research: [Canva AI Connector](https://www.canva.com/ai-connector/),
[Stripe MCP on ChatGPT](https://marketplace.stripe.com/apps/mcp-chatgpt) and
[OpenAI's useful-app guidance](https://developers.openai.com/blog/what-makes-a-great-chatgpt-app).
The page applies their task-first framing and concrete examples while retaining
Avalou's identity and verified FreeAgent AI workflow boundaries.

The approval section pairs a single approval sentence with Tima Miroshnichenko's
[stock photograph of accounting work](https://www.pexels.com/photo/an-accountant-s-workspace-6694492/),
self-hosted as `accounting-review.webp` under the [Pexels licence](https://www.pexels.com/license/).
The image is decorative marketing imagery and does not depict a product user.

Workflow examples use the [shadcn line-tab pattern](https://ui.shadcn.com/docs/components/base/tabs#line),
adapted to the existing static HTML/CSS/JavaScript runtime. Selecting a tab shows
only its associated panel. Arrow keys, Home/End, roving tab focus, ARIA panel
relationships, direct hash links and browser history are supported. With
JavaScript disabled, the same links navigate the fully visible source content.
The tab strip scrolls horizontally on small screens without widening the page.

The connection steps become an accordion when JavaScript is available. All three
titles are visible initially; opening a step closes the previous one. Native
buttons expose their expanded state and panel relationships. Details animate
open and closed, with transitions removed for reduced-motion preferences. Without
JavaScript, all instructions remain readable. The Avalou monogram matches the
website hover rotation and also responds to keyboard focus.

## Public static site

`python -m freeagent_ai.landing --static --output build/landing` exports the
marketing page with both connections disabled, the account navigation replaced
with an on-page explanation, and local privacy/terms/support pages. The
privacy notice covers the website and connected service; the terms describe product use. Review the
wording in the implementation PR. Publishing these pages does not approve public
OAuth access or complete the connected-service privacy review.
The normal `--config` and `FREEAGENT_LANDING_CONFIG` launch gates are unchanged.

The application's CI deploys this export after all checks pass on a push to main,
using its existing production Workload Identity Federation identity. PR builds
cannot deploy. `hosting.json` contains the website's headers and backend rewrite;
`scripts/publish_landing.py` uploads and verifies the release. The infrastructure
repository manages Firebase APIs, site, custom domain and the CI identity's IAM
grant, and relinquishes the former config-only content version/release.

Merge the infrastructure handover and apply its reviewed IAM grant before merging
the application deployment. Cloud Run remains private. CI verifies public pages
and protected backend routes after publishing. No server credentials enter the export.


Deployment identity, cloud project, registry, backend service/region and Hosting
site are supplied through protected deployment-environment secrets. `hosting.json`
contains public headers only; the publisher injects the exact backend rewrite
from private configuration and validates all returned resource names against the
configured project/site. Public CI summaries contain the build digest only.

## Social previews

The homepage includes Open Graph and Twitter large-image card metadata. Both use
`/landing-assets/social-card-v1.png`, a 1200×630 PNG composed from the site's
existing palette and licensed fonts, with the product logo from
`publication/assets/icon.svg` beside the title and a smaller Avalou publisher
credit. It ships in the wheel and static export.
Use a new versioned filename when replacing the image to refresh crawler caches.
After deployment, check the public homepage with a social-card validator; local
export checks do not prove that a third-party crawler has refreshed its preview.

When both provider connections are disabled, the hero states that connections are
not publicly available yet and links “Contact us about access” to the configured
support page (`/support/` in the public static export). The support page provides
the public email contact. Enabling either verified provider destination removes
this fallback, leaving the available connection as the call to action.
