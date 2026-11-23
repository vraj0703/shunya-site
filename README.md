# shunya-site

shunya.systems: `/` is Shunya Systems, `/tantr/` is tantr, each a first page and a case study in four
articles (`/articles/<slug>/`, `/tantr/articles/<slug>/`). Plain HTML, CSS and JS; no framework, no
third-party script (TANTR-6).

## The words and the pages

- `articles/<site>/00-home.json`: the first page's words (`title`, `description`, `button`, `meta`).
- `articles/<site>/NN-slug.html`: an article. The first line is an HTML comment holding JSON
  `{"title","short","summary","slug","order","minutes"}` (`short` is the first page's link label);
  the rest is a body fragment in plain semantic HTML. The build refuses anything that runs or loads.
- `templates/`: `home.html` (Vishal's wireframe: mark and name, what it is, Request access, the four
  links; the animated panel on the right; stacked on a phone), `article.html` (one readable column,
  Request access at the end, previous and next) and `request.html` (the form, in a dialog).

`tools/build.py` renders them into `dist/` with the assets. To try the site on the pc:

    powershell -File tools\write-config.ps1     # on the pc, from .secret\logger.env
    python tools/build.py && python -m http.server 8080 --directory dist

## Request access (SHUNY-13)

Every Request access button opens the same form: an e-mail address (required), a name and one line on
what they would use it for (both optional). Sending it takes two roads at once, and it counts when
either arrives. One is tantr's own: a `collect.submission` envelope (formId `access_request`, version
1, the whole request) to `https://tantr.app/v0/envelopes`, kept in the server's up journal
(`GET /v0/admin/up`). The other is one event, `access_requested`, to PostHog's capture endpoint with
the project's public client token: `distinct_id` is the address, properties are `email`, `site`
(`shunya` | `tantr`), `has_name`, `has_reason` (whether they were given, never what they say),
`page`, `referrer` and any `utm_*`, and `$set.email` puts the address on the person. In PostHog:
Activity (events) filtered to `access_requested`, or People. The earlier `waitlist_joined` events stay
where they are.

`config.js` holds the token and is **not** in the repo (the build writes it from the environment).

`python test/e2e.py` (playwright and chromium) builds the site into a temporary folder and walks it:
both first pages, the eight articles from their links, the form on both roads against fake endpoints,
phone widths, framing. `python tools/share_images.py` redraws the two share images from the marks and
the first sentence of each description.

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
