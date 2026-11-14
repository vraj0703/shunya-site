# shunya-site

The waitlist pages: `/` is Shunya Systems, `/tantr/` is tantr. Plain HTML, CSS and JS; no build
step, no third-party script (TANTR-6).

Pressing **Join** sends the signup down two roads at once, and it counts when either arrives.
One is tantr's own: a `collect.submission` envelope (formId `waitlist`, version 2) to
`https://tantr.app/v0/envelopes`, kept in the server's up journal (`GET /v0/admin/up`). The other is one event, `waitlist_joined`, to PostHog's capture endpoint with the
project's public client token: `distinct_id` is the address, properties are `email`, `site`
(`shunya` | `tantr`), `page`, `referrer` and any `utm_*`, and `$set.email` puts the address on the
person. In PostHog: Activity (events) filtered to `waitlist_joined`, or People.

`config.js` holds the token and is **not** in the repo. To try the site on the pc, write it first:

    powershell -File tools\write-config.ps1     # on the pc, from .secret\logger.env

Try it: `python -m http.server 8080` in this folder, open http://localhost:8080/ and /tantr/.

## Hosting: Cloudflare Workers (static assets)

The Worker `shunya-systems-site` is connected to this repository: a push to `main` builds and goes
live; a pull request gets a preview. `wrangler.jsonc` tells it to serve `dist/`, which
`tools/build.py` makes (the pages and assets only, `config.js` from the build variables, a
`_headers` file and a 404 page). `.github/workflows/deploy.yml` runs the end-to-end test and
checks the build beside it.

One-time setup in the Cloudflare dashboard (Vishal's hand), Worker > Settings:

1. Build: build command `python3 tools/build.py`, deploy command `npx wrangler deploy`.
2. Build > Variables and secrets: `POSTHOG_TOKEN` = the PostHog project token (`phc_...`).
3. Domains & Routes > Add > Custom domain > `shunya.systems` (and `www.shunya.systems`). The zone
   is on Cloudflare, so the DNS record and the certificate are created for you.

The build refuses a token that is not a `phc_` project token.

Known limit: with an ad blocker that stops PostHog the signup still arrives on tantr's road, but
it is then missing from PostHog until the server forwards submissions (tantr-app PR 12).
