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

## Hosting: Cloudflare Pages

Cloudflare builds and deploys from this repository. A push to `main` goes live; a pull request
gets a preview URL that Cloudflare comments on the PR. `.github/workflows/deploy.yml` runs the
end-to-end test and checks the build beside it.

One-time setup in the Cloudflare dashboard (Vishal's hand):

1. Workers & Pages > Create > Pages > Connect to Git > `vraj0703/shunya-site`, production branch `main`.
2. Build command `python3 tools/build.py`, build output directory `dist`, no framework preset.
3. Settings > Variables and secrets: `POSTHOG_TOKEN` = the PostHog project token (`phc_...`), for
   Production and Preview. Optional `POSTHOG_HOST`.
4. Custom domains > Set up a domain > `shunya.systems` (and `www.shunya.systems`). The zone is
   already on Cloudflare, so the DNS record and the certificate are created for you.

`tools/build.py` copies only the pages and assets into `dist/`, writes `config.js` from those
variables and a `_headers` file. It refuses a token that is not a `phc_` project token.

Known limit: with an ad blocker that stops PostHog the signup still arrives on tantr's road, but
it is then missing from PostHog until the server forwards submissions (tantr-app PR 12).
