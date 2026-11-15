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

## Build logs: Cloudflare to the logger and PostHog

Cloudflare's build log lives in its dashboard. `.github/workflows/build-log.yml` copies each build's
outcome there too: when Cloudflare's check on a commit completes, `tools/build_log.py` reads the build
id from the check's link, fetches the log from Cloudflare's API and posts one record to the tantr
logger (`https://logs.tantr.app/ingest`), which forwards it to PostHog as a log line, as an event
`cloudflare_build_finished`, and, for a failed build, as an error `CloudflareBuildFailed` with the
last error line. The record carries worker, branch, commit, conclusion and the last 80 log lines.

Two repository secrets switch it on (Settings > Secrets and variables > Actions):

- `LOGS_API_KEY`: an ingest key of the logger. The logger's `LOGS_API_KEYS` must hold
  `shunya-site=<that key>`; another app name goes in the repository variable `LOGS_APP`.
- `CLOUDFLARE_API_TOKEN`: a user-scoped API token (an account-scoped one is refused by the builds
  API) with Workers Builds Configuration. Try Read first; Cloudflare's page names Edit.

Without the first nothing is sent; without the second the outcome is sent without the log. Neither
case fails the run. `python test/build_log_test.py` checks the script without the network.
